from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Add email column
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN email VARCHAR(150) UNIQUE"))
            print("Added email column.")
        except Exception as e:
            print(f"Email column might already exist: {e}")
            db.session.rollback()

        # Add must_change_password column
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN must_change_password BOOLEAN DEFAULT TRUE"))
            print("Added must_change_password column.")
        except Exception as e:
            print(f"must_change_password column might already exist: {e}")
            db.session.rollback()
            
        db.session.commit()
        print("Migration complete.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
