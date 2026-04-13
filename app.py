import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, EmailField
from wtforms.validators import DataRequired, Email, EqualTo
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message

# --- Application Setup ---
load_dotenv() # Load environment variables from .env

# --- Forms ---

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class InviteForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    can_view = BooleanField('Can View Dashboard', default=True)
    can_edit = BooleanField('Can Edit (Add Questions)', default=False)
    is_admin = BooleanField('Is Admin', default=False)
    submit = SubmitField('Invite User')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change Password')

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-this-later")
# Use Neon DB if available, else fallback to SQLite
database_url = os.environ.get("DATABASE_URL", "sqlite:///project.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@questionary.app')

# Upload Configuration
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Initialize Serializer and Mail
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
mail = Mail(app)

db.init_app(app)

# --- Database Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=True) # Optional now
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for first-time users
    is_admin = db.Column(db.Boolean, default=False)
    can_view = db.Column(db.Boolean, default=True)
    can_edit = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employees = db.relationship('Employee', backref='department', lazy=True)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    position = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    questions = db.relationship('Question', backref='employee', lazy=True)
    tasks = db.relationship('Task', backref='employee', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=True)
    answer_text = db.Column(db.Text)
    question_image = db.Column(db.String(255))
    answer_image = db.Column(db.String(255))
    # Status: 'Pending', 'Answered', 'Follow-up'
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime)
    # tag column is ignored/deprecated
    parent_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=True)
    
    children = db.relationship('Question', backref=db.backref('parent', remote_side=[id]), cascade="all, delete-orphan", lazy=True)

    @property
    def repetition_count(self):
        # Count this question (1) + all its children EXCLUDING deleted employees
        if self.parent_id:
            return 0 
        
        # Check if the main question's employee is deleted
        base_count = 1 if not self.employee.is_deleted else 0
        
        # Count children whose employees are not deleted
        child_count = sum(1 for child in self.children if not child.employee.is_deleted)
        
        return base_count + child_count

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255))
    # Status: 'Pending', 'In Progress', 'Completed' - though user said they don't need statuses, 
    # but some internal status might be useful for 'data' tracking.
    # User said: "i dont need statuses, as it is only data"
    # Actually, I'll just keep it simple as requested.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    parent_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    
    children = db.relationship('Task', backref=db.backref('parent', remote_side=[id]), cascade="all, delete-orphan", lazy=True)

    @property
    def repetition_count(self):
        if self.parent_id:
            return 0
        base_count = 1 if not self.employee.is_deleted else 0
        child_count = sum(1 for child in self.children if not child.employee.is_deleted)
        return base_count + child_count

class BreachIncident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=False)
    incident_date = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.Text)
    financial_impact = db.Column(db.Float)  # Pillar 1
    downtime_days = db.Column(db.Integer)    # Pillar 3
    strategic_severity = db.Column(db.Integer) # Pillar 4 (0-5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sentiments = db.relationship('SentimentResponse', backref='incident', lazy=True)

class SentimentResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('breach_incident.id'), nullable=False)
    stakeholder_type = db.Column(db.String(100)) # e.g., 'Customer', 'Employee', 'Shareholder'
    trust_score = db.Column(db.Integer) # 1-10
    sentiment_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Routes ---

# --- Auth Routes ---



@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email:
            flash('Please enter your email.', 'danger')
            return redirect(url_for('login'))
        
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        is_first_user = (User.query.count() == 0)
        
        # If password provided, try password login
        if password:
            if user and user.check_password(password):
                login_user(user)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password', 'danger')
                return redirect(url_for('login'))
        
        # No password provided - send magic link
        if not user and not is_first_user:
            flash('Access denied. Your email is not authorized.', 'danger')
            return redirect(url_for('login'))
            
        if is_first_user:
            # Create the first user as Admin automatically
            user = User(email=email, is_admin=True, can_view=True, can_edit=True)
            db.session.add(user)
            db.session.commit()
            print(f"First user created as ADMIN: {email}")

        # Generate Magic Link
        token = serializer.dumps(email, salt='login-salt')
        link = url_for('login_callback', token=token, _external=True)
        
        # Send Email
        try:
            if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                msg = Message(
                    subject='Your Login Link - Questionary',
                    recipients=[email],
                    body=f'''Hello,

Click the link below to log in to Questionary:

{link}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.

Best regards,
Questionary Team'''
                )
                mail.send(msg)
                print(f"Email sent to {email}")
            else:
                # Development mode - print to console
                print(f"--- MAGIC LOGIN LINK ---", flush=True)
                print(f"To: {email}", flush=True)
                print(f"Link: {link}", flush=True)
                print(f"------------------------", flush=True)
        except Exception as e:
            print(f"Error sending email: {e}")
            # Fallback to console
            print(f"--- MAGIC LOGIN LINK ---", flush=True)
            print(f"To: {email}", flush=True)
            print(f"Link: {link}", flush=True)
            print(f"------------------------", flush=True)
        
        flash('Check your email for the login link!', 'info')
        return render_template('login_sent.html', email=email)
        
    return render_template('login.html')

@app.route('/auth/callback/<token>')
def login_callback(token):
    try:
        email = serializer.loads(token, salt='login-salt', max_age=3600) # 1 hour
    except Exception:
        flash('The login link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))
        
    user = User.query.filter_by(email=email).first()
    if user:
        login_user(user)
        # Check if user needs to set password
        if not user.password_hash:
            flash('Please create a password for your account.', 'info')
            return redirect(url_for('set_password'))
        flash('Logged in successfully!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('User not found.', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/set-password', methods=['GET', 'POST'])
@login_required
def set_password():
    # If user already has a password, redirect to dashboard
    if current_user.password_hash:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('set_password'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('set_password'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('set_password'))
        
        # Set password
        current_user.set_password(password)
        db.session.commit()
        
        flash('Password created successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('set_password.html')

@app.route('/register/<token>', methods=['GET', 'POST'])
def register_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    try:
        # Validate token (valid for 24 hours = 86400 sec)
        data = serializer.loads(token, salt='invite-salt', max_age=86400)
    except Exception:
        flash('The invitation link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))
    
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken. Please choose another.', 'warning')
        else:
            new_user = User(
                username=form.username.data,
                email=data['email'],
                is_admin=data['is_admin'],
                can_view=data['can_view'],
                can_edit=data['can_edit'],
                must_change_password=False # They just set it
            )
            new_user.set_password(form.password.data)
            db.session.add(new_user)
            db.session.commit()
            flash('Account created! You can now login.', 'success')
            return redirect(url_for('login'))
            
    return render_template('register.html', form=form, email=data['email'])

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.check_password(form.old_password.data):
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            flash('Password updated successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect current password.', 'danger')
    return render_template('change_password.html', form=form)

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.is_admin:
        flash('Access Denied: Admin only.', 'danger')
        return redirect(url_for('dashboard'))
    
    invite_form = InviteForm()
    if invite_form.validate_on_submit():
        email = invite_form.email.data
        
        # Check if email already used
        if User.query.filter_by(email=email).first():
            flash('User with this email already exists.', 'warning')
        else:
            # Add User Directly
            new_user = User(
                email=email,
                is_admin=invite_form.is_admin.data,
                can_view=invite_form.can_view.data,
                can_edit=invite_form.can_edit.data
            )
            db.session.add(new_user)
            db.session.commit()
            
            # Optionally send them a link immediately?
            # For now just say they are added
            flash(f'User {email} added to whitelist.', 'success')
            return redirect(url_for('admin'))
    
    users = User.query.all()
    return render_template('admin.html', users=users, invite_form=invite_form)

@app.route('/admin/user/delete/<int:id>')
@login_required
def delete_user(id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('Cannot delete main admin.', 'danger')
    else:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted.', 'success')
    return redirect(url_for('admin'))

# --- Main Routes ---

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.can_view:
        flash('You do not have permission to view the dashboard.', 'warning')
        return render_template('base.html') # Minimal view

    total_questions = Question.query.count()
    pending_questions = Question.query.filter_by(status='Pending').count()
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    status_filter = request.args.get('status')
    
    # Sort by Department Name, then by Date
    query = db.session.query(Question).join(Employee).join(Department)
    
    if status_filter:
        query = query.filter(Question.status == status_filter)
        
    questions_pagination = query.order_by(Department.name, Question.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    all_questions = questions_pagination.items
    
    # Get top recurring questions (parents with children)
    recurring_questions = [q for q in Question.query.all() if q.repetition_count > 1]
    recurring_questions.sort(key=lambda x: x.repetition_count, reverse=True)
    
    # Get employees for the Add Question modal (only non-deleted)
    employees = Employee.query.filter_by(is_deleted=False).all()
    
    return render_template('dashboard.html', 
                           total_questions=total_questions,
                           pending_questions=pending_questions,
                           recent_questions=all_questions,
                           recurring_questions=recurring_questions[:5],
                           employees=employees,
                           pagination=questions_pagination,
                           per_page=per_page,
                           current_status=status_filter)

@app.route('/questions/<int:id>/view')
@login_required
def view_question(id):
    """View a single question with its details."""
    if not current_user.can_view:
        flash('Access Denied', 'danger')
        return redirect(url_for('index'))
    
    question = Question.query.get_or_404(id)
    employees = Employee.query.filter_by(is_deleted=False).all()
    all_questions = Question.query.order_by(Question.created_at.desc()).all()
    
    return render_template('questions.html', 
                           questions=[question], 
                           employees=employees,
                           single_view=True)

@app.route('/cyber-impact')
@login_required
def cyber_impact():
    incidents = BreachIncident.query.order_by(BreachIncident.incident_date.desc()).all()
    
    # Process incidents to include their scorecard data
    processed_incidents = []
    for inc in incidents:
        score, pillar_scores = calculate_impact_score(inc)
        chart_data = generate_radar_chart(pillar_scores)
        processed_incidents.append({
            'incident': inc,
            'score': score,
            'chart': chart_data
        })
        
    return render_template('scorecard.html', incidents=processed_incidents)

@app.route('/cyber-impact/add', methods=['POST'])
@login_required
def add_incident():
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('cyber_impact'))
        
    company_name = request.form.get('company_name')
    incident_date_str = request.form.get('incident_date')
    description = request.form.get('description')
    financial_impact = request.form.get('financial_impact', 0)
    downtime_days = request.form.get('downtime_days', 0)
    strategic_severity = request.form.get('strategic_severity', 0)
    
    try:
        incident_date = datetime.strptime(incident_date_str, '%Y-%m-%d')
        new_inc = BreachIncident(
            company_name=company_name,
            incident_date=incident_date,
            description=description,
            financial_impact=float(financial_impact),
            downtime_days=int(downtime_days),
            strategic_severity=int(strategic_severity)
        )
        db.session.add(new_inc)
        db.session.commit()
        flash('Breach incident added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding incident: {e}', 'danger')
        
    return redirect(url_for('cyber_impact'))

@app.route('/questions', methods=['GET', 'POST'])
@login_required
def questions():
    if not current_user.can_view:
        flash('Access Denied', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if not current_user.can_edit:
            flash('You do not have permission to add questions.', 'danger')
            return redirect(url_for('questions'))

        employee_id = request.form.get('employee_id')
        question_text = request.form.get('question_text')
        parent_id = request.form.get('parent_id')
        
        # Handle empty string from form
        if not parent_id:
            parent_id = None
        
        question_image_filename = None
        if 'question_image' in request.files:
            file = request.files['question_image']
            if file and allowed_file(file.filename):
                extension = file.filename.rsplit('.', 1)[1].lower()
                question_image_filename = f"{uuid.uuid4()}.{extension}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], question_image_filename))

        if employee_id and (question_text or question_image_filename):
            new_q = Question(
                employee_id=employee_id, 
                question_text=question_text, 
                parent_id=parent_id,
                question_image=question_image_filename
            )
            db.session.add(new_q)
            db.session.commit()
            flash('Question added successfully!', 'success')
        return redirect(url_for('questions'))
        return redirect(url_for('questions'))
        
    all_questions = Question.query.order_by(Question.created_at.desc()).all()
    employees = Employee.query.filter_by(is_deleted=False).all()
    return render_template('questions.html', questions=all_questions, employees=employees)

@app.route('/questions/<int:id>/update', methods=['POST'])
def update_question(id):
    q = Question.query.get_or_404(id)
    answer_text = request.form.get('answer_text')
    status = request.form.get('status')
    question_text_edit = request.form.get('question_text_edit')
    
    if status == 'Answered' and (not answer_text or not answer_text.strip()):
        flash('Cannot mark as Answered without providing an answer.', 'danger')
        # Try to redirect back to referrer, otherwise go to questions page
        return redirect(request.referrer or url_for('questions'))
    
    # Handle admin question text edit
    if question_text_edit and current_user.is_admin:
        if question_text_edit.strip():
            q.question_text = question_text_edit.strip()

    # Handle answer image upload
    if 'answer_image' in request.files:
        file = request.files['answer_image']
        if file and allowed_file(file.filename):
            extension = file.filename.rsplit('.', 1)[1].lower()
            answer_image_filename = f"{uuid.uuid4()}.{extension}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], answer_image_filename))
            q.answer_image = answer_image_filename

    q.answer_text = answer_text
    q.status = status
    if q.status == 'Answered' and not q.answered_at:
        q.answered_at = datetime.utcnow()
    
    db.session.commit()
    flash('Question updated!', 'success')
    # Redirect back to where the user came from
    return redirect(request.referrer or url_for('questions'))

@app.route('/questions/<int:id>/edit', methods=['POST'])
@login_required
def edit_question(id):
    if not current_user.is_admin:
        flash('Access Denied: Only admins can edit questions.', 'danger')
        return redirect(url_for('questions'))
    
    q = Question.query.get_or_404(id)
    new_question_text = request.form.get('question_text')
    
    if not new_question_text or not new_question_text.strip():
        flash('Question text cannot be empty.', 'danger')
        return redirect(url_for('questions'))
    
    q.question_text = new_question_text
    db.session.commit()
    flash('Question text updated successfully!', 'success')
    return redirect(url_for('questions'))

@app.route('/questions/<int:id>/delete', methods=['POST'])
@login_required
def delete_question(id):
    if not current_user.is_admin:
        flash('Access Denied: Only admins can delete questions.', 'danger')
        return redirect(url_for('dashboard'))
        
    q = Question.query.get_or_404(id)
    db.session.delete(q)
    db.session.commit()
    flash('Question deleted successfully.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/departments', methods=['GET', 'POST'])
def departments():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            existing = Department.query.filter_by(name=name).first()
            if not existing:
                db.session.add(Department(name=name))
                db.session.commit()
                flash(f'Department {name} created!', 'success')
            else:
                flash(f'Department {name} already exists.', 'warning')
        return redirect(url_for('departments'))
    
    all_depts = Department.query.all()
    return render_template('departments.html', departments=all_depts)

@app.route('/departments/<int:id>/update', methods=['POST'])
@login_required
def update_department(id):
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('departments'))
    
    dept = Department.query.get_or_404(id)
    name = request.form.get('name')
    if name:
        dept.name = name
        db.session.commit()
        flash(f'Department updated to {name}.', 'success')
    return redirect(url_for('departments'))

@app.route('/departments/<int:id>/delete', methods=['POST'])
@login_required
def delete_department(id):
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('departments'))
    
    dept = Department.query.get_or_404(id)
    if dept.employees:
        flash('Cannot delete department with active employees.', 'danger')
    else:
        db.session.delete(dept)
        db.session.commit()
        flash('Department deleted.', 'success')
    return redirect(url_for('departments'))

@app.route('/employees', methods=['GET', 'POST'])
def employees():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        department_id = request.form.get('department_id')
        position = request.form.get('position')
        
        if full_name and department_id:
            new_emp = Employee(full_name=full_name, department_id=department_id, position=position)
            db.session.add(new_emp)
            db.session.commit()
            flash('Employee added!', 'success')
        return redirect(url_for('employees'))
    
    all_emps = Employee.query.filter_by(is_deleted=False).all()
    departments = Department.query.all()
    return render_template('employees.html', employees=all_emps, departments=departments)

@app.route('/employees/<int:id>/update', methods=['POST'])
@login_required
def update_employee(id):
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('employees'))
    
    emp = Employee.query.get_or_404(id)
    emp.full_name = request.form.get('full_name')
    emp.department_id = request.form.get('department_id')
    emp.position = request.form.get('position')
    emp.is_active = 'is_active' in request.form
    
    db.session.commit()
    flash('Employee info updated!', 'success')
    return redirect(url_for('employees'))

@app.route('/employees/<int:id>/delete', methods=['POST'])
@login_required
def delete_employee(id):
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('employees'))
    
    emp = Employee.query.get_or_404(id)
    # User wanted: "if i delete the employee, dont dlete the questions that gave only that employee"
    # So we soft-delete
    emp.is_deleted = True
    db.session.commit()
    flash(f'Employee {emp.full_name} has been deactivated/deleted.', 'success')
    return redirect(url_for('employees'))

# --- Task Routes ---

@app.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    if not current_user.can_view:
        flash('Access Denied', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if not current_user.can_edit:
            flash('Access Denied', 'danger')
            return redirect(url_for('tasks'))

        employee_id = request.form.get('employee_id')
        description = request.form.get('description')
        link = request.form.get('link')
        parent_id = request.form.get('parent_id') or None
        
        if employee_id and description:
            new_task = Task(
                employee_id=employee_id,
                description=description,
                link=link,
                parent_id=parent_id
            )
            db.session.add(new_task)
            db.session.commit()
            flash('Task added successfully!', 'success')
        return redirect(url_for('tasks'))

    all_tasks = Task.query.order_by(Task.created_at.desc()).all()
    employees = Employee.query.filter_by(is_deleted=False).all()
    return render_template('tasks.html', tasks=all_tasks, employees=employees)

@app.route('/tasks/<int:id>/delete', methods=['POST'])
@login_required
def delete_task(id):
    if not current_user.is_admin:
        flash('Access Denied', 'danger')
        return redirect(url_for('tasks'))
    
    task = Task.query.get_or_404(id)
    db.session.delete(task)
    db.session.commit()
    flash('Task deleted.', 'success')
    return redirect(url_for('tasks'))

@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database tables created.")

    # Seed data if empty
    if Department.query.count() == 0:
        d1 = Department(name="IT")
        d2 = Department(name="HR")
        d3 = Department(name="Sales")
        db.session.add_all([d1, d2, d3])
        db.session.commit()
        
        e1 = Employee(full_name="Alice Smith", department=d1, position="Sys Admin")
        e2 = Employee(full_name="Bob Jones", department=d2, position="Recruiter")
        db.session.add_all([e1, e2])
        db.session.commit()
        
        q1 = Question(employee_id=e1.id, question_text="How do I reset the server password?", status="Pending")
        db.session.add(q1)
        db.session.commit()
        print("Seeded database with initial data.")

if __name__ == '__main__':
    app.run(debug=True)
