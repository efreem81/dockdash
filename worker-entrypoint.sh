#!/bin/bash
set -euo pipefail

umask 077
chmod 700 /app/data
for database_file in /app/data/dockdash.db /app/data/dockdash.db-wal /app/data/dockdash.db-shm; do
    if [[ -e "$database_file" ]]; then
        chmod 600 "$database_file"
    fi
done

exec python dockdash_cli.py job-worker
