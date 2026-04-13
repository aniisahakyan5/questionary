import sqlite3
import os

def migrate():
    db_path = 'instance/project.db'
    if not os.path.exists(db_path):
        db_path = 'project.db'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add question_image column
        cursor.execute("ALTER TABLE question ADD COLUMN question_image VARCHAR(255)")
        print("Added column question_image")
    except sqlite3.OperationalError as e:
        print(f"Could not add question_image: {e}")

    try:
        # Add answer_image column
        cursor.execute("ALTER TABLE question ADD COLUMN answer_image VARCHAR(255)")
        print("Added column answer_image")
    except sqlite3.OperationalError as e:
        print(f"Could not add answer_image: {e}")

    # Note: SQLite doesn't support ALTER TABLE to change nullability directly in a simple way
    # (it requires renaming, recreating, and copying). 
    # However, existing rows will work with NULL question_text if the ORM allows it, 
    # and new rows will follow the new schema if the table is recreated or if we just rely on SQLAlchemy.
    # Given the risk of table recreation, we'll stick to adding columns for now.
    
    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
