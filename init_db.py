#!/usr/bin/env python
"""
Database initialization script.
Run this before starting the application to ensure the database is ready.
"""

import os
import sys
import time


def _secure_database_files(db_dir):
    os.chmod(db_dir, 0o700)
    for filename in ('dockdash.db', 'dockdash.db-wal', 'dockdash.db-shm'):
        path = os.path.join(db_dir, filename)
        if os.path.exists(path):
            os.chmod(path, 0o600)

def init_database():
    """Initialize the database."""
    # Ensure data directory exists with proper permissions
    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

    old_umask = os.umask(0o077)
    try:
        os.makedirs(db_dir, exist_ok=True, mode=0o700)
        _secure_database_files(db_dir)
    except Exception as e:
        print(f"Error: Could not secure data directory: {e}", file=sys.stderr)
        return 1
    finally:
        os.umask(old_umask)

    # Give the mount point time to become available
    max_retries = 5
    for attempt in range(max_retries):
        if os.access(db_dir, os.W_OK):
            break

        if attempt < max_retries - 1:
            print(f"Data directory not ready, retrying... ({attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(1)
        else:
            print(f"Error: {db_dir} is not writable", file=sys.stderr)
            return 1

    # Initialize and validate the application after securing its storage.
    try:
        from config import create_app
        create_app({'INITIALIZE_DATABASE': True})
        _secure_database_files(db_dir)
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        return 1

    print("Database initialization complete")
    return 0

if __name__ == '__main__':
    sys.exit(init_database())
