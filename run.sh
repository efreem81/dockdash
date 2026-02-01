#!/bin/bash
# Build and run DockDash

set -e

# Ensure data directory exists on host for bind mount
mkdir -p data
chmod 755 data

get_host_ip() {
  # Try to get the default route interface IP
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}'
    return
  fi

  # macOS fallback
  if command -v ipconfig >/dev/null 2>&1; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null
    return
  fi

  # Last resort
  hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost"
}

# Auto-set HOST_IP if not configured
if [[ -f .env ]]; then
  if ! grep -qE '^HOST_IP=.+' .env || grep -qE '^HOST_IP=$' .env; then
    HOST_IP="$(get_host_ip)"
    if [[ -n "$HOST_IP" && "$HOST_IP" != "localhost" ]]; then
      echo "HOST_IP=${HOST_IP}" >> .env
      echo "Auto-detected HOST_IP=${HOST_IP}"
    fi
  fi
fi

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
