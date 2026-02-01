#!/usr/bin/env bash
set -euo pipefail

# DockDash - Build, Run, and Deploy
# Usage:
#   ./deploy.sh           # Full build and start (pulls git if available)
#   ./deploy.sh --quick   # Quick restart without rebuild
#   ./deploy.sh --logs    # Show logs after starting

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}===${NC} $1"; }
warn() { echo -e "${YELLOW}===${NC} $1"; }
error() { echo -e "${RED}===${NC} $1" >&2; }

# Check for docker
if ! command -v docker >/dev/null 2>&1; then
  error "Error: docker is not installed or not on PATH."
  exit 1
fi

# Prefer 'docker compose' (v2), fall back to 'docker-compose' (v1)
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  error "Error: Docker Compose is not installed."
  exit 1
fi

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

generate_secret_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex(32))"
  else
    LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 64
    echo
  fi
}

ensure_env_file() {
  if [[ -f .env ]]; then
    # Update HOST_IP if it's empty or placeholder
    if ! grep -qE '^HOST_IP=.+' .env || grep -qE '^HOST_IP=$' .env || grep -qE '^HOST_IP=192\.168\.0\.100$' .env; then
      local host_ip
      host_ip="$(get_host_ip)"
      if [[ -n "$host_ip" && "$host_ip" != "localhost" ]]; then
        if grep -qE '^HOST_IP=' .env; then
          if sed --version >/dev/null 2>&1; then
            sed -i -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
          else
            sed -i '' -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
          fi
        else
          echo "HOST_IP=${host_ip}" >> .env
        fi
        log "Set HOST_IP=${host_ip}"
      fi
    fi
    return
  fi

  # Create .env from template
  if [[ ! -f .env.example ]]; then
    error ".env not found and .env.example is missing."
    exit 1
  fi

  cp .env.example .env
  log "Created .env from .env.example"

  # Generate secret key
  local secret_key host_ip
  secret_key="$(generate_secret_key)"
  host_ip="$(get_host_ip)"

  if sed --version >/dev/null 2>&1; then
    sed -i -E "s/^SECRET_KEY=.*/SECRET_KEY=${secret_key}/" .env
    [[ -n "$host_ip" && "$host_ip" != "localhost" ]] && sed -i -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
  else
    sed -i '' -E "s/^SECRET_KEY=.*/SECRET_KEY=${secret_key}/" .env
    [[ -n "$host_ip" && "$host_ip" != "localhost" ]] && sed -i '' -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
  fi

  log "Generated SECRET_KEY"
  [[ -n "$host_ip" && "$host_ip" != "localhost" ]] && log "Set HOST_IP=${host_ip}"
}

# Ensure data directory exists
mkdir -p data
chmod 755 data

# Pull latest code if in a git repo
if [[ -d .git ]]; then
  log "Pulling latest changes..."
  git pull
fi

# Ensure .env exists with proper values
ensure_env_file

# Build and deploy
SHOW_LOGS=false
QUICK=false

for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=true ;;
    --logs) SHOW_LOGS=true ;;
  esac
done

if [[ "$QUICK" == "true" ]]; then
  log "Quick restart (no rebuild)..."
  "${COMPOSE[@]}" up -d
else
  log "Building DockDash..."
  "${COMPOSE[@]}" build --no-cache
  log "Starting DockDash..."
  "${COMPOSE[@]}" up -d
fi

# Wait and show status
sleep 2
echo ""
"${COMPOSE[@]}" ps

if [[ "$SHOW_LOGS" == "true" ]]; then
  echo ""
  log "Container Logs:"
  "${COMPOSE[@]}" logs --tail=50 dockdash
fi

# Show access info
PORT=$(grep -E '^DOCKDASH_PORT=' .env 2>/dev/null | cut -d= -f2 || echo "9999")
HOST_IP=$(grep -E '^HOST_IP=' .env 2>/dev/null | cut -d= -f2 || echo "localhost")
echo ""
log "DockDash is ready!"
echo "    Local:   http://localhost:${PORT}"
echo "    Network: http://${HOST_IP}:${PORT}"
