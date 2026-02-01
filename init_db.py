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
    # Ensure data directory exists
    db_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(db_dir, exist_ok=True)
    
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
            return 1

if __name__ == '__main__':
    sys.exit(init_database())
