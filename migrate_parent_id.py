from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE question ADD COLUMN parent_id INTEGER REFERENCES question(id)"))
        db.session.commit()
        print("Column 'parent_id' added successfully.")
    except Exception as e:
        print(f"Error (might be skipped if exists): {e}")
