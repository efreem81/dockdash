#!/bin/bash

echo "DockDash is starting..."

# Ensure data directory exists and is writable
mkdir -p /app/data
chmod 755 /app/data

# Run database initialization
python init_db.py || {
    echo "Database initialization had issues, but continuing..."
    # Don't exit on database error - it might initialize on first request
}

# Get the port from environment or use default
PORT=${DOCKDASH_PORT:-9999}
echo "DockDash ready! Open: http://localhost:${PORT}"

# Start Gunicorn with extended timeout for long-running operations (vulnerability scans)
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 600 app:app
