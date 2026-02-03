#!/usr/bin/env python
"""
Database initialization script.
Run this before starting the application to ensure the database is ready.
"""

import os
import sys
import time

def init_database():
    """Initialize the database."""
    # Ensure data directory exists with proper permissions
    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    
    try:
        os.makedirs(db_dir, exist_ok=True, mode=0o755)
    except Exception as e:
        print(f"Warning: Could not create data directory: {e}", file=sys.stderr)
    
    # Give the mount point time to become available
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # Check if directory is writable
            if os.access(db_dir, os.W_OK):
                break
        except Exception:
            pass
        
        if attempt < max_retries - 1:
            print(f"Data directory not ready, retrying... ({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(1)
        else:
            print(f"Warning: {db_dir} may not be writable", file=sys.stderr)
    
    # Import app after ensuring directory exists
    try:
        from config import create_app, db
        from models import User
        app = create_app()
    except Exception as e:
        print(f"Error importing app: {e}", file=sys.stderr)
        return 1
    
    with app.app_context():
        try:
            print("Creating database tables...")
            db.create_all()
            print("Database tables created successfully")
            
            # Check if default user exists
            if User.query.count() == 0:
                print("Creating default user...")
                default_username = os.environ.get('DEFAULT_USERNAME', 'admin')
                default_password = os.environ.get('DEFAULT_PASSWORD', 'dockdash')
                user = User(username=default_username)
                user.set_password(default_password)
                db.session.add(user)
                db.session.commit()
                print(f"Created default user: {default_username}")
            else:
                print("Default user already exists")
            
            print("Database initialization complete")
            return 0
        except Exception as e:
            print(f"Error initializing database: {e}", file=sys.stderr)
            # Don't fail - database might initialize on first request
            return 0

if __name__ == '__main__':
    sys.exit(init_database())
