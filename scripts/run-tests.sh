#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="dockdash-precommit-tests:local"

docker build --quiet --file "$repository_dir/tests/Dockerfile" --tag "$image_name" "$repository_dir" >/dev/null
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --volume "$repository_dir:/app:ro" \
  --workdir /app \
  --env SECRET_KEY=test-only \
  --env DEFAULT_PASSWORD=test-only-password \
  "$image_name" python -m unittest discover -s tests -v
