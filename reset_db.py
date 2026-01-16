from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # Drop the table if it exists
        db.session.execute(text("DROP TABLE IF EXISTS \"user\" CASCADE"))
        db.session.commit()
        print("User table dropped.")
        
        # Create it again with new schema
        db.create_all()
        print("Tables created (User table recreated).")
        
    except Exception as e:
        print(f"Error: {e}")
