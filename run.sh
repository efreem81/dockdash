#!/bin/bash
# Build and run DockDash

set -e

# Ensure data directory exists on host for bind mount
mkdir -p data
chmod 755 data

echo "=== Building DockDash ==="
docker compose build --no-cache

echo ""
echo "=== Starting DockDash ==="
docker compose up -d

echo ""
echo "=== Waiting for container to start ==="
sleep 2

echo ""
echo "=== Container Status ==="
docker compose ps

echo ""
echo "=== Container Logs ==="
docker compose logs dockdash

echo ""
PORT=$(grep DOCKDASH_PORT .env | cut -d= -f2 || echo "9999")
echo "=== DockDash is ready! ==="
echo "Open: http://localhost:${PORT}"
