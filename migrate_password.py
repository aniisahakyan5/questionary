from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Add password_hash column
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN password_hash VARCHAR(255)"))
        db.session.commit()
        print("Added password_hash column successfully.")
    except Exception as e:
        print(f"Error (column might already exist): {e}")
        db.session.rollback()
