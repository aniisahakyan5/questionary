import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///project.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@questionary.app')

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    questions = db.relationship('Question', backref='employee', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text)
    # Status: 'Pending', 'Answered', 'Follow-up'
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime)
    # tag column is ignored/deprecated
    parent_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=True)
    
    children = db.relationship('Question', backref=db.backref('parent', remote_side=[id]), lazy=True)

    @property
    def repetition_count(self):
        # Count this question (1) + all its children
        if self.parent_id:
            # If I am a child, look at my parent's count? Or just say I'm a duplicate?
            # User wants "Asked X times" on the main question.
            return 0 
        return 1 + len(self.children)

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
    
    # Sort by Department Name, then by Date
    all_questions = db.session.query(Question).join(Employee).join(Department).order_by(Department.name, Question.created_at.desc()).all()
    
    # Get top recurring questions (parents with children)
    recurring_questions = [q for q in Question.query.all() if q.repetition_count > 1]
    recurring_questions.sort(key=lambda x: x.repetition_count, reverse=True)
    
    return render_template('dashboard.html', 
                           total_questions=total_questions,
                           pending_questions=pending_questions,
                           recent_questions=all_questions,
                           recurring_questions=recurring_questions[:5])

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
        
        if employee_id and question_text:
            new_q = Question(employee_id=employee_id, question_text=question_text, parent_id=parent_id)
            db.session.add(new_q)
            db.session.commit()
            flash('Question added successfully!', 'success')
        return redirect(url_for('questions'))
        return redirect(url_for('questions'))
        
    all_questions = Question.query.order_by(Question.created_at.desc()).all()
    employees = Employee.query.filter_by(is_active=True).all()
    return render_template('questions.html', questions=all_questions, employees=employees)

@app.route('/questions/<int:id>/update', methods=['POST'])
def update_question(id):
    q = Question.query.get_or_404(id)
    answer_text = request.form.get('answer_text')
    status = request.form.get('status')
    
    if status == 'Answered' and (not answer_text or not answer_text.strip()):
        flash('Cannot mark as Answered without providing an answer.', 'danger')
        return redirect(url_for('questions'))

    q.answer_text = answer_text
    q.status = status
    if q.status == 'Answered' and not q.answered_at:
        q.answered_at = datetime.utcnow()
    
    db.session.commit()
    flash('Question updated!', 'success')
    return redirect(url_for('questions'))

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
    
    all_emps = Employee.query.all()
    departments = Department.query.all()
    return render_template('employees.html', employees=all_emps, departments=departments)

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
