from app import app, db, User, Department, Employee, Question

with app.app_context():
    # Delete all data
    Question.query.delete()
    Employee.query.delete()
    Department.query.delete()
    User.query.delete()
    
    db.session.commit()
    print("✅ Database cleared successfully!")
    print("All users, departments, employees, and questions have been removed.")
    print("The database is now empty and ready for production.")
