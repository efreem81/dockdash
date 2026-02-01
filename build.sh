#!/usr/bin/env bash
set -euo pipefail

# Build and start DockDash using Docker Compose.
# Usage:
#   ./build.sh
#   DOCKDASH_PORT=9090 ./build.sh

if command -v docker >/dev/null 2>&1; then
  :
else
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

# Prefer 'docker compose' (v2), fall back to 'docker-compose' (v1).
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Error: Docker Compose is not installed (need 'docker compose' or 'docker-compose')." >&2
  exit 1
fi

# Ensure we're running from the repository root (where docker-compose.yml lives).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

generate_secret_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
    return
  fi

  # Last-resort fallback.
  LC_ALL=C tr -dc 'a-f0-9' </dev/urandom | head -c 64
  echo
}

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

ensure_env_file() {
  if [[ -f .env ]]; then
    return
  fi

  if [[ ! -f .env.example ]]; then
    echo "Error: .env not found and .env.example is missing." >&2
    exit 1
  fi

  cp .env.example .env

  local secret_key
  secret_key="$(generate_secret_key)"

  if grep -qE '^SECRET_KEY=' .env; then
    # macOS sed uses -i '' while GNU sed uses -i
    if sed --version >/dev/null 2>&1; then
      sed -i -E "s/^SECRET_KEY=.*/SECRET_KEY=${secret_key}/" .env
    else
      sed -i '' -E "s/^SECRET_KEY=.*/SECRET_KEY=${secret_key}/" .env
    fi
  else
    printf '\nSECRET_KEY=%s\n' "$secret_key" >> .env
  fi

  # Auto-detect and set HOST_IP if not already set
  if ! grep -qE '^HOST_IP=.+' .env || grep -qE '^HOST_IP=$' .env || grep -qE '^HOST_IP=192\.168\.0\.100$' .env; then
    local host_ip
    host_ip="$(get_host_ip)"
    if [[ -n "$host_ip" && "$host_ip" != "localhost" ]]; then
      if sed --version >/dev/null 2>&1; then
        sed -i -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
      else
        sed -i '' -E "s/^HOST_IP=.*/HOST_IP=${host_ip}/" .env
      fi
      echo "Set HOST_IP=${host_ip}"
    fi
  fi

  echo "Created .env from .env.example and generated SECRET_KEY."
}

ensure_env_file

# Build and start services.
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d

HOST_PORT="${DOCKDASH_PORT:-8080}"
echo "DockDash is starting. Open: http://localhost:${HOST_PORT}"

# Show status to confirm it's up.
"${COMPOSE[@]}" ps
