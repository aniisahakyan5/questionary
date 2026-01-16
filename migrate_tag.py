from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Check if column exists first to be safe, or just catch the error
        db.session.execute(text("ALTER TABLE question ADD COLUMN tag VARCHAR(50)"))
        db.session.commit()
        print("Column 'tag' added successfully.")
    except Exception as e:
        print(f"Error (might be skipped if exists): {e}")
