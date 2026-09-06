#!/bin/bash
set -euo pipefail

umask 077

echo "DockDash is starting..."

# Ensure data directory exists and is writable
mkdir -p /app/data
chmod 700 /app/data

# Run database initialization
python init_db.py
chmod 700 /app/data
for database_file in /app/data/dockdash.db /app/data/dockdash.db-wal /app/data/dockdash.db-shm; do
    if [[ -e "$database_file" ]]; then
        chmod 600 "$database_file"
    fi
done
export DOCKDASH_SKIP_DB_INIT=1

# Get the port from environment or use default
PORT=${DOCKDASH_PORT:-9999}
echo "DockDash ready! Open: http://localhost:${PORT}"

# Start Gunicorn with extended timeout for long-running operations (vulnerability scans)
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 600 app:app
