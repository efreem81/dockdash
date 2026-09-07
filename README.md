# DockDash

DockDash is a self-hosted Docker fleet and Compose management application. It
provides the multi-host inventory, container lifecycle, project orchestration,
and deployment workflow needed by this project without a node-based commercial
license gate.

The intended operator is a trusted administrator. RBAC, Kubernetes, and Swarm
management are not current goals.

## What it manages

- Multiple standalone Docker hosts through certificate-authenticated agents.
- A consolidated, read-only all-host container view plus live endpoint health;
  unreachable or powered-off hosts are reported without hiding reachable inventory.
- Container inventory, details, stats, logs, start, stop, restart, removal, and
  local-only exec.
- Image inventory, pull, deletion, per-host registry update checks,
  dangling-image and unused-volume cleanup, and per-host Trivy scanning.
- Existing Compose projects discovered from Docker labels and allowlisted host
  directories, then adopted without rewriting them.
- Compose validate, start, stop, restart, pull, up, recreate, logs, scale, and
  down without volume deletion.
- Compose-aware remediation from container details, security findings, project
  groups, selected containers, or all known updates. The update workflow pulls
  current tags, redeploys only the intended running services, verifies health,
  and refreshes update and vulnerability evidence.
- New DockDash-managed Compose definitions and Git-backed deployments.
- Required-mount, free-capacity, Compose, Docker health, and optional HTTP
  application checks.
- Durable serialized jobs with before/after image state and deployment revision
  evidence.
- Webhook monitoring, shared service links, and a responsive web UI.

Remote agents do not expose the Docker Engine API. They expose a deliberately
narrow HTTPS API and require mutual TLS. Plain HTTP and certificate-less access
are not supported.

## Scope and limitations

DockDash is Docker-first. Local Podman socket compatibility may continue to work
through the Docker SDK compatibility layer, but the fleet agent, Compose
orchestration, deployment validation, and release gate target Docker Engine and
Docker Compose v2.

DockDash does not currently provide:

- RBAC, teams, or multi-tenant isolation;
- Kubernetes or Swarm orchestration;
- arbitrary remote shell or remote container exec;
- automatic recreation of standalone remote containers (adopt them into
  Compose first);
- automatic application-data rollback;
- volume-destructive Compose teardown; or
- controller high availability or horizontal scaling.

Unused-volume prune is available and affects every unused volume on the selected
endpoint. Treat it as a destructive host-wide action; it is not a routine
troubleshooting step.

An administrator and every DockDash component with Docker socket access are
effectively root-equivalent on the managed host. Read the
[security model](docs/SECURITY.md) before deployment.

## Architecture

```text
Browser -- HTTPS --> DockDash controller/UI -- mTLS --> host agent -- Docker socket
                         |                                |
                         +-- SQLite                       +-- Docker Compose v2
                         +-- single durable worker        +-- allowlisted host paths
```

The controller-host agent has no published port and shares a private Docker
bridge with the controller worker. Remote agents bind TCP/9002 to an exact
management address, and host forwarding policy must allow that port only from
the controller.

See [Docker fleet architecture](docs/ARCHITECTURE.md) for endpoint scoping,
project sources, job flow, preflight checks, and revision behavior.

## Quick start

### Prerequisites

- Docker Engine
- Docker Compose v2
- OpenSSL for fleet certificate enrollment
- `pre-commit` for the complete release gate

### Start the controller

```bash
git clone git@github.com:efreem81/dockdash.git
cd dockdash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
SECRET_KEY=generate-a-random-64-hex-character-value
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=choose-a-unique-initial-password
DOCKDASH_PORT=9999
HOST_IP=192.168.1.50
```

Generate `SECRET_KEY` with:

```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

Then deploy:

```bash
./deploy.sh
curl --fail http://127.0.0.1:9999/health
```

`deploy.sh` creates the private `dockdash-control` network when needed, refuses
blank/known default passwords, protects `.env`, builds the images, and starts
the controller and worker. `./deploy.sh --quick` skips the rebuild and should be
used only when the existing image is intentionally retained.

The initial password is used only if the database has no user. Change it after
first login. Put the UI behind an HTTPS reverse proxy for production and set:

```env
SESSION_COOKIE_SECURE=1
REMEMBER_COOKIE_SECURE=1
```

Do not publish TCP/9999 directly to the internet.

## Secure fleet setup

### 1. Create the CA and controller identity

On the CA/controller host:

```bash
docker network create dockdash-control
sudo install -d -m 0700 /etc/dockdash-pki
sudo agent/scripts/create-ca-controller.sh /etc/dockdash-pki
install -d -m 0700 data/pki
sudo install -m 0444 /etc/dockdash-pki/ca.crt data/pki/ca.crt
sudo install -m 0444 /etc/dockdash-pki/controller.crt data/pki/controller.crt
sudo install -m 0400 /etc/dockdash-pki/controller.key data/pki/controller.key
```

Keep `/etc/dockdash-pki/ca.key` root-only and offline except while signing or
rotating certificates. Never copy it to an agent.

### 2. Create each agent identity

Generate the private key and CSR on the agent host:

```bash
sudo install -d -m 0700 /etc/dockdash-agent
sudo agent/scripts/create-server-csr.sh /etc/dockdash-agent HOSTNAME
```

Transfer only the CSR to the CA host. Review and sign it with the exact IP or DNS
name the controller will use:

```bash
sudo agent/scripts/sign-server-csr.sh \
  /etc/dockdash-pki server.csr server.crt IP:192.0.2.10
```

Return only `server.crt` and `ca.crt` to the agent. The agent's `server.key`
never leaves that host.

### 3. Deploy the agent

Use:

- `agent/compose.controller.yaml` on the controller host;
- `agent/compose.yaml` where adopted Compose roots are needed; or
- `agent/compose.opt-only.yaml` for managed `/opt` deployments only.

Remote deployments require `DOCKDASH_AGENT_BIND` to be the exact management IP:

```bash
DOCKDASH_AGENT_BIND=192.0.2.10 \
  docker compose -f agent/compose.yaml config --quiet
DOCKDASH_AGENT_BIND=192.0.2.10 \
  docker compose -f agent/compose.yaml up -d --build
```

Before opening TCP/9002, install a persistent `DOCKER-USER` or equivalent
forwarding rule that allows only the controller and rejects other sources.

### 4. Accept and register the host

Verify the certificate chain/SAN, an authorized mTLS request, a failed request
without a client certificate, a denied request from another host, and the
read-only/capability-dropped agent runtime. In the UI, add the exact HTTPS URL in
**Fleet**, test it, select it, and use **Projects → Discover / adopt**.

Certificates created by the supplied scripts are valid for 397 days. Monitor
expiry and rotate them before that date. See the [operations
runbook](docs/OPERATIONS.md) for the complete procedure.

## Operating projects

Discovery records projects from Compose labels first and scans configured roots
for stopped projects. It excludes backup and archive trees. Adoption does not
rewrite existing definitions.

Before changing a project:

1. Select the exact endpoint.
2. Configure required storage mountpoints and an application health URL when
   appropriate.
3. Run **Validate**.
4. Submit the narrow lifecycle/deployment action.
5. Wait for the durable job to report `succeeded` or `failed`.
6. Review output, application health, and revision image IDs.

The worker serializes mutations and recovers interrupted jobs after restart.
Start-like actions avoid silently starting intentionally stopped services when
no service list is supplied.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | required | Flask session signing key |
| `DEFAULT_USERNAME` | `admin` | Initial username when no user exists |
| `DEFAULT_PASSWORD` | required for first user | Unique initial password |
| `DOCKDASH_PORT` | `9999` | Controller host port |
| `HOST_IP` | auto-detected by deploy script | Address used for local container links |
| `SESSION_COOKIE_SECURE` | `0` | Require HTTPS for session cookie |
| `REMEMBER_COOKIE_SECURE` | `0` | Require HTTPS for remember cookie |
| `SESSION_LIFETIME_HOURS` | `12` | Session lifetime |
| `AUTO_START_MONITORING` | `0` | Start background monitoring at controller startup |
| `DOCKDASH_AGENT_CA` | `/app/data/pki/ca.crt` | Controller agent CA bundle |
| `DOCKDASH_AGENT_CERT` | `/app/data/pki/controller.crt` | Controller client certificate |
| `DOCKDASH_AGENT_KEY` | `/app/data/pki/controller.key` | Controller client key |
| `DOCKDASH_AGENT_TIMEOUT` | `30` | Default agent request timeout in seconds |

Agent variables:

| Variable | Default | Purpose |
|---|---|---|
| `DOCKDASH_AGENT_BIND` | none; remote deployment fails | Exact remote management bind address |
| `DOCKDASH_COMPOSE_ROOTS` | definition-specific | Allowed resolved project/config roots |
| `DOCKDASH_SCAN_ROOTS` | Compose roots | Roots scanned for stopped projects |
| `DOCKDASH_MANAGED_ROOT` | `/opt/dockdash-managed` | Writable managed/Git project root |
| `DOCKDASH_AGENT_MIN_FREE_BYTES` | `1073741824` | Minimum free bytes for preflight |
| `DOCKDASH_AGENT_MAX_OUTPUT` | `50000` | Maximum returned command-output characters |
| `DOCKDASH_AGENT_MAX_SCAN_RESULT_BYTES` | `33554432` | Maximum accepted Trivy JSON result size per image |
| `DOCKDASH_AGENT_MAX_SCAN_FINDINGS` | `5000` | Maximum detailed findings returned per image; summary counts remain complete |
| `DOCKDASH_AGENT_UPDATE_REGISTRIES` | public registry allowlist | Registries an agent may contact for update checks |
| `DOCKDASH_AGENT_UPDATE_AUTH_HOSTS` | public auth-host allowlist | HTTPS bearer-token hosts accepted from registry challenges |

The agent resolves vulnerability targets through its local Docker daemon and
passes the immutable local image ID to Trivy. Update checks permit outbound
requests only to the configured registry and token-host allowlists. Private
registries must be explicitly added and must provide an authentication method
available to the agent; credentials are not accepted in image references.

## Administrative CLI

Run the CLI inside the controller container so it uses the same database and
PKI paths:

```bash
docker compose exec dockdash python dockdash_cli.py endpoint-list
docker compose exec dockdash python dockdash_cli.py endpoint-test --name HOST
docker compose exec dockdash python dockdash_cli.py project-sync --endpoint HOST
docker compose exec dockdash python dockdash_cli.py project-validate \
  --endpoint HOST --project PROJECT
docker compose exec dockdash python dockdash_cli.py project-action \
  --endpoint HOST --project PROJECT --action restart
```

## Development and validation

Create a virtual environment for local work:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r agent/requirements.txt
```

Run the complete repository gate before committing:

```bash
pre-commit run --all-files
```

The gate checks repository hygiene and private keys, YAML, Python lint and
security, controller and agent dependency vulnerabilities, shell scripts, the
controller/agent regression suite, JavaScript syntax, all Compose definitions,
clean controller/agent image builds, Trivy actionable High/Critical findings,
and authorized/unauthorized/TLS-version/runtime mTLS behavior.

## Documentation

- [Docker fleet architecture](docs/ARCHITECTURE.md)
- [Operations runbook](docs/OPERATIONS.md)
- [Security model](docs/SECURITY.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Agent deployment notes](agent/README.md)
- [February 2026 assessment (historical)](docs/ASSESSMENT.md)

## License

DockDash is licensed under the [MIT License](LICENSE).
