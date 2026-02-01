#!/usr/bin/env python
"""
Database initialization script.
Run this before starting the application to ensure the database is ready.
"""

import os
import sys
from app import app, db, init_default_user

def init_database():
    """Initialize the database."""
    # Ensure data directory exists with proper permissions
    db_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(db_dir, exist_ok=True, mode=0o755)
    
    # Ensure the directory is writable
    if not os.access(db_dir, os.W_OK):
        print(f"Warning: {db_dir} is not writable. Attempting to fix permissions...", file=sys.stderr)
        try:
            os.chmod(db_dir, 0o755)
        except Exception as e:
            print(f"Failed to change permissions: {e}", file=sys.stderr)
    
    with app.app_context():
        try:
            print("Creating database tables...")
            db.create_all()
            print("Database tables created successfully")
            
            print("Initializing default user...")
            init_default_user()
            print("Database initialization complete")
            return 0
        except Exception as e:
            print(f"Error initializing database: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1

if __name__ == '__main__':
    sys.exit(init_database())
