from app import app, db
from sqlalchemy import text
from werkzeug.security import generate_password_hash

with app.app_context():
    try:
        # Create User table
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS "user" (
                id SERIAL PRIMARY KEY,
                username VARCHAR(150) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                can_view BOOLEAN DEFAULT TRUE,
                can_edit BOOLEAN DEFAULT FALSE
            );
        """))
        db.session.commit()
        print("User table created.")

        # Check if admin exists
        admin_exists = db.session.execute(text("SELECT * FROM \"user\" WHERE username = 'admin'")).fetchone()
        if not admin_exists:
            pw_hash = generate_password_hash('admin123')
            db.session.execute(text(f"INSERT INTO \"user\" (username, password_hash, is_admin, can_view, can_edit) VALUES ('admin', '{pw_hash}', TRUE, TRUE, TRUE)"))
            db.session.commit()
            print("Default admin user created.")
        else:
            print("Admin user already exists.")
            
    except Exception as e:
        print(f"Error: {e}")
