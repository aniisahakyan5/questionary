from app import app, serializer

with app.app_context():
    token = serializer.dumps('admin@test.com', salt='login-salt')
    print(f"http://127.0.0.1:5000/auth/callback/{token}")
