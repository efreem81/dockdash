# DockDash Agent

The agent exposes a narrow Docker and Compose API over mutually authenticated TLS. It does not expose the Docker Engine API directly.

Required certificate files in `/etc/dockdash-agent`:

- `ca.crt`
- `server.crt`
- `server.key`

The controller uses its own CA-signed client certificate. Agents accept connections only from clients presenting a certificate signed by that CA. The agent has no plaintext mode, requires TLS 1.2 or newer, and its server certificate must contain the endpoint hostname or IP as a subject alternative name.

Use `scripts/create-ca-controller.sh`, `scripts/create-server-csr.sh`, and
`scripts/sign-server-csr.sh` for reproducible certificate creation. The server
key is generated on—and never leaves—the agent host. The CA key remains
root-only on the controller/CA host. Leaf certificates are valid for 397 days;
record their expiry in monitoring and rotate them before that date.

Use `compose.controller.yaml` on the DockDash controller host. It exposes no host port and uses the private external `dockdash-control` bridge. Use `compose.yaml` on hosts with both recorded Compose roots and `compose.opt-only.yaml` on `/opt`-only hosts. Remote deployments require an explicit `DOCKDASH_AGENT_BIND` management address; there is no all-interface default.

The controller-host definition also mounts `/home/eric/Compose-Examples` because several recorded files under `/home/eric/docker-compose` resolve there through symlinks. Path authorization always checks the resolved target, so an unmounted or unlisted symlink cannot escape the configured roots.

Adopted Compose trees and `/home/eric/docker` are mounted read-only. Compose can
read existing definitions and `env_file` references, but DockDash cannot rewrite
them. Only `/opt`, which contains the allowlisted managed deployment root, is
writable.

`/mnt` is also read-only inside the agent. This allows required-mount preflight checks to distinguish a mounted NAS/filesystem from an ordinary empty directory without granting deployment code write access to media data.

Configure `DOCKDASH_COMPOSE_ROOTS` as a comma-separated allowlist. Project paths outside those roots are rejected. DockDash-managed and Git deployments are stored below `DOCKDASH_MANAGED_ROOT`.

The agent intentionally does not expose `docker compose down -v`, arbitrary shell execution, or a general host filesystem API.

The supplied Compose definitions also use a read-only container root filesystem,
drop every Linux capability, disable privilege escalation, and provide bounded
temporary filesystems only for process and Docker CLI state.

Because the agent controls a Docker socket, compromise of the agent is
root-equivalent on that Docker host. Bind remote TCP/9002 to the exact
management IP and enforce a persistent `DOCKER-USER` or equivalent forwarding
rule that allows only the DockDash controller. Validate both a permitted mTLS
request and a rejected request from another source after every firewall or
Docker restart.
