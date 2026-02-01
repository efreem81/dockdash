#!/bin/bash
set -e

echo "DockDash is starting..."

# Run database initialization
python init_db.py

# Get the port from environment or use default
PORT=${DOCKDASH_PORT:-9999}
echo "DockDash ready! Open: http://localhost:${PORT}"

# Start Gunicorn
exec gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
