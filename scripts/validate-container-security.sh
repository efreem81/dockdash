#!/usr/bin/env bash
set -euo pipefail

repository_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
validation_id="${PPID}-$$"
controller_image="dockdash-precommit-controller:${validation_id}"
agent_image="dockdash-precommit-agent:${validation_id}"
agent_container="dockdash-precommit-agent-${validation_id}"
certificate_dir="$(mktemp -d /tmp/dockdash-mtls.XXXXXX)"

cleanup() {
  docker container rm --force "$agent_container" >/dev/null 2>&1 || true
  docker image rm --force "$controller_image" "$agent_image" >/dev/null 2>&1 || true
  find "$certificate_dir" -type f -delete
  rmdir "$certificate_dir"
}
trap cleanup EXIT HUP INT TERM

docker build --tag "$controller_image" "$repository_dir"
docker build --tag "$agent_image" "$repository_dir/agent"

docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=4g \
  --volume /var/run/docker.sock:/var/run/docker.sock:ro \
  --env CONTROLLER_IMAGE="$controller_image" \
  --env AGENT_IMAGE="$agent_image" \
  --entrypoint /bin/sh \
  "$controller_image" -c 'set -eu
    trivy image --cache-dir /tmp/trivy --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$CONTROLLER_IMAGE"
    trivy image --cache-dir /tmp/trivy --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$AGENT_IMAGE"
  '

"$repository_dir/agent/scripts/create-ca-controller.sh" "$certificate_dir"
"$repository_dir/agent/scripts/create-server-csr.sh" "$certificate_dir" localhost
"$repository_dir/agent/scripts/sign-server-csr.sh" \
  "$certificate_dir" "$certificate_dir/server.csr" "$certificate_dir/server.crt" DNS:localhost
# The validation key is ephemeral and owned by the invoking developer. The
# capability-free root process cannot bypass DAC ownership as it does for the
# root-owned 0400 production key, so make this disposable copy readable.
chmod 0444 "$certificate_dir/server.key"
chmod 0755 "$certificate_dir"

agent_port="$(python3 -c 'import socket; sock = socket.socket(); sock.bind(("127.0.0.1", 0)); print(sock.getsockname()[1]); sock.close()')"
docker run --detach --rm \
  --name "$agent_container" \
  --userns host \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:rw,noexec,nosuid,size=2g \
  --tmpfs /root/.docker:rw,noexec,nosuid,size=16m \
  --publish "127.0.0.1:${agent_port}:9002" \
  --volume /var/run/docker.sock:/var/run/docker.sock:rw \
  --volume "$certificate_dir:/certs:ro" \
  "$agent_image" >/dev/null

authenticated=false
for _attempt in $(seq 1 30); do
  if curl --silent --show-error --fail \
      --cacert "$certificate_dir/ca.crt" \
      --cert "$certificate_dir/controller.crt" \
      --key "$certificate_dir/controller.key" \
      "https://localhost:${agent_port}/health" >/dev/null; then
    authenticated=true
    break
  fi
  sleep 1
done
if [[ "$authenticated" != true ]]; then
  echo 'Authenticated mTLS health check failed' >&2
  docker logs "$agent_container" >&2
  exit 1
fi

scanner_status="$(curl --silent --show-error --fail \
  --cacert "$certificate_dir/ca.crt" \
  --cert "$certificate_dir/controller.crt" \
  --key "$certificate_dir/controller.key" \
  "https://localhost:${agent_port}/v1/security/status")"
python3 -c 'import json, sys
payload = json.loads(sys.argv[1])
if not payload.get("success") or not payload.get("available") or payload.get("scanner") != "trivy":
    raise SystemExit(f"Agent scanner status is not ready: {payload}")' "$scanner_status"

if curl --silent --show-error --fail \
    --cacert "$certificate_dir/ca.crt" \
    "https://localhost:${agent_port}/health" >/dev/null 2>&1; then
  echo 'Agent accepted a TLS connection without a client certificate' >&2
  exit 1
fi

if curl --silent --show-error --fail --tls-max 1.1 \
    --cacert "$certificate_dir/ca.crt" \
    --cert "$certificate_dir/controller.crt" \
    --key "$certificate_dir/controller.key" \
    "https://localhost:${agent_port}/health" >/dev/null 2>&1; then
  echo 'Agent accepted obsolete TLS below version 1.2' >&2
  exit 1
fi

runtime_settings="$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.CapDrop}} {{.HostConfig.SecurityOpt}}' "$agent_container")"
if [[ "$runtime_settings" != *'true'* || "$runtime_settings" != *'ALL'* || "$runtime_settings" != *'no-new-privileges:true'* ]]; then
  echo "Agent runtime hardening is incomplete: $runtime_settings" >&2
  exit 1
fi
