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
        from app import app, db, init_default_user
    except Exception as e:
        print(f"Error importing app: {e}", file=sys.stderr)
        return 1
    
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
            # Don't fail - database might initialize on first request
            return 0

if __name__ == '__main__':
    sys.exit(init_database())
