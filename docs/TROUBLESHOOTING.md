# DockDash troubleshooting

Start with observation. Do not delete the database, remove volumes, recreate a
workload, or weaken TLS to diagnose a failure.

## First response

From the controller directory:

```bash
git rev-parse HEAD
docker compose ps
docker compose images
docker compose logs --tail=100 dockdash dockdash-worker
curl --fail http://127.0.0.1:9999/health
stat -c '%a %U:%G %n' data data/dockdash.db data/pki data/pki/controller.key
```

Expected controller state:

- `dockdash` is healthy and `/health` reports `status: ok`,
  `database_ok: true`, and `docker_available: true`.
- `dockdash-worker` is running. It intentionally has no container health check.
- `data/` is mode `0700`, SQLite files are `0600`, the PKI directory is `0700`,
  and the controller private key is `0400`.
- The deployed image was built from the intended Git revision. Compare embedded
  files or build metadata; a recent container start time is not enough.

## Controller does not start

### Missing `SECRET_KEY` or `DEFAULT_PASSWORD`

The application deliberately fails closed without `SECRET_KEY`. It also requires
`DEFAULT_PASSWORD` when the database contains no user. Set values in the
root-only `.env` file and redeploy:

```bash
chmod 600 .env
docker compose config --quiet
docker compose up -d --build
```

Do not put real secrets in Compose files, Git, issue reports, or diagnostic
output.

### Database or migration error

Read the complete startup error first:

```bash
docker compose logs --tail=200 dockdash
df -h data
df -i data
stat -c '%a %U:%G %n' data data/dockdash.db 2>/dev/null
```

The startup path validates every required table and column. Do not bypass a
migration failure or create an empty replacement database. Take a consistent
backup, retain the failing database, and repair or restore it.

To inspect schema health without printing application records:

```bash
docker compose exec dockdash python -c \
  "from config import database_schema_errors; print(database_schema_errors())"
```

An empty list is expected.

### `/health` returns 503

The response identifies whether Docker or the database schema is unavailable.
Check both the socket mount and schema; a running Gunicorn process is not enough.

## Docker inventory is empty

Confirm the intended endpoint is selected. Then test it in **Fleet**.

For the controller container:

```bash
docker compose exec dockdash python -c \
  "import docker; c=docker.from_env(); print(c.version()); print(len(c.containers.list(all=True)))"
```

For a remote endpoint, continue with the mTLS and network checks below. An
offline or intentionally sleeping host should be recorded as such; do not start
it merely to clear a dashboard error unless that power transition is intended.

## Agent is unreachable

Work through the layers in order.

### 1. Container and bind address

On the agent host:

```bash
docker compose ps
docker compose logs --tail=100 dockdash-agent
docker inspect dockdash-agent --format \
  'readonly={{.HostConfig.ReadonlyRootfs}} caps={{json .HostConfig.CapDrop}} security={{json .HostConfig.SecurityOpt}} ports={{json .NetworkSettings.Ports}}'
```

A remote listener must bind the exact management IP. An error requiring
`DOCKDASH_AGENT_BIND` is intentional; do not replace it with `0.0.0.0`.

The controller-host agent has no published host port and is reachable by the
worker through the `dockdash-control` network.

### 2. Certificate chain, purpose, name, and time

On the agent, inspect metadata only:

```bash
openssl verify -CAfile /etc/dockdash-agent/ca.crt \
  -purpose sslserver /etc/dockdash-agent/server.crt
openssl x509 -in /etc/dockdash-agent/server.crt \
  -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
```

On the controller, verify the client certificate:

```bash
openssl verify -CAfile data/pki/ca.crt \
  -purpose sslclient data/pki/controller.crt
openssl x509 -in data/pki/controller.crt \
  -noout -subject -issuer -dates -ext extendedKeyUsage
```

Common causes:

- Endpoint URL does not exactly match an IP/DNS SAN.
- Agent and controller use different CAs.
- A server-only certificate was installed as the controller client identity.
- Certificate is expired or not yet valid because a host clock is wrong.
- A key does not match its certificate.

Check a key/certificate match without displaying private material:

```bash
openssl x509 -in server.crt -pubkey -noout | sha256sum
openssl pkey -in server.key -pubout | sha256sum
```

The hashes must match.

### 3. Mutual TLS behavior

Run the authenticated request from the controller runtime, where its certificate
paths and the agent network are available. Then try a request without a client
certificate; it must fail. Do not use `-k`, disable verification, change the
endpoint to HTTP, or enable redirects as a workaround.

### 4. Host forwarding policy

Docker-published agent ports are filtered through forwarding policy, usually
`DOCKER-USER`, not only INPUT/UFW. Confirm:

- established traffic is permitted;
- original-destination TCP/9002 from the controller is permitted;
- other source addresses are dropped; and
- rules persist after Docker and host restarts.

Test from both an authorized controller source and a denied source. A TCP timeout
from every source usually means routing/firewall; a TLS alert after connection
usually means certificate authentication.

## Endpoint selection error

Errors such as `Docker endpoint was not found` or `Docker endpoint is disabled`
are fail-closed behavior. Refresh **Fleet**, select the intended enabled host,
and retry. Never change the code to fall back to the first host: that can perform
an operation on the wrong Docker daemon.

If a project URL returns 404, confirm that the project belongs to the selected
endpoint. Project IDs are scoped by endpoint even if another host has a project
with the same name.

## A vulnerable container cannot be updated

Open the container detail or its vulnerability badge. An adopted, running
Compose service offers **Pull, redeploy & rescan**. DockDash queues a durable
project job and reports deployment, health-check, registry-check, and rescan
failures through that job.

If the UI offers **Adopt into Compose**, the container is standalone or its
Compose project has not been discovered. Use **Compose Projects → Discover /
adopt** and verify that the project directory is within the agent's allowlisted
roots. DockDash intentionally does not reconstruct standalone remote containers
from Docker inspect data.

If findings remain after a successful update, inspect whether the registry
published a newer digest for the current tag. A package may have a published
fix while the selected image tag still contains the vulnerable package; change
the image tag in the owning Compose definition when appropriate and deploy the
project again.

If **Scan Now** fails, confirm the selected endpoint reports Trivy as available
under **Security**. Container-detail scanning resolves and scans the image on
the owning agent; it does not scan through the controller or accept a remote
filesystem target.

## Project discovery misses a Compose project

On the owning host, inspect the running container labels:

```bash
docker inspect CONTAINER --format '{{json .Config.Labels}}'
```

Confirm:

- `com.docker.compose.project.working_dir` points to the real owning directory;
- the directory and all resolved symlink targets are mounted into the agent;
- the resolved paths are below `DOCKDASH_COMPOSE_ROOTS`;
- the directory is below a configured scan root if no labeled container is
  running;
- the directory is not an archive/backup tree; and
- the Compose filename is one of `compose.yaml`, `compose.yml`,
  `docker-compose.yaml`, or `docker-compose.yml`.

Do not widen roots to `/` or mount an entire home directory just to make a
project appear. Add the narrow required path and redeploy the agent.

## Validation fails

### Insufficient free space

The default minimum is 1 GiB at the project working directory. Check both blocks
and inodes:

```bash
df -h PROJECT_DIRECTORY
df -i PROJECT_DIRECTORY
```

Free capacity through the workload's normal retention/cleanup process. Do not
run a full Docker prune through the agent; it is intentionally unavailable.

### Required mount is unavailable

DockDash uses mountpoint semantics, not directory existence:

```bash
mountpoint /expected/path
findmnt /expected/path
```

An empty directory left behind after an NFS/storage failure must not pass. Restore
the storage dependency and validate again.

### Compose configuration is invalid

Run validation from the exact recorded working directory and with every recorded
Compose file:

```bash
cd PROJECT_DIRECTORY
docker compose config --quiet
```

Check missing `env_file` paths, unresolved variables, invalid YAML, and symlinked
files. Keep secrets out of copied diagnostic output.

## Job remains queued or running

Check the worker:

```bash
docker compose ps dockdash-worker
docker compose logs --tail=200 dockdash-worker
```

Only one worker can hold the shared lock. A second worker should exit with
`Another DockDash project worker is already active`. Do not remove the lock file
while a worker process is alive.

After a crash/restart, interrupted `running` jobs should return to `queued` and
be reclaimed. If a job fails, read its `stage`, `error`, and bounded output in
the Projects view. Correct the cause and submit a new action; do not edit job
status directly in SQLite.

## Lifecycle action surprises

- `start`, `restart`, `up`, `recreate`, and `scale` do not implicitly select
  intentionally stopped services when no services are supplied.
- `down` removes project containers/networks and orphans but never volumes.
- Remote container exec is deliberately rejected. Use an audited host access
  path when interactive troubleshooting is required.
- Remote full system prune is deliberately rejected. Unused-volume prune is
  available, is host-wide and destructive, and must not be used as a diagnostic
  shortcut.

## Application health check fails

From the agent host, test the exact URL without embedding credentials:

```bash
curl --head --max-time 10 http://service.example/health
```

Confirm DNS, routing, certificate trust, response time, and expected status.
DockDash accepts 200–399 by default. Configure exact accepted status codes only
when the response is intentionally healthy (for example, a documented 401
authentication challenge). Do not accept 500-series responses simply to make a
deployment green.

## Git-backed refresh fails

Check repository reachability, ref name, credential mechanism, Compose path, and
free space. Repository URLs containing embedded credentials should be rejected
operationally even if Git accepts them.

The agent validates a staged clone before promotion. Confirm the active checkout
was not changed and inspect the managed backup directory. Do not manually delete
the active checkout until the backup and failed staging state are understood.

## Container links point to the wrong host

Set `HOST_IP` to the address clients use for the selected local Docker host and
redeploy the controller. A published TCP port is shown as a web link only when
the probe confirms HTTP or HTTPS; databases, SSH, MQTT, and other protocols are
correctly left non-clickable.

## Safe diagnostic bundle

Collect metadata without environment values, certificate contents, Compose
rendering, or database records:

```bash
git rev-parse HEAD
docker version
docker compose version
docker compose ps
docker compose images
docker compose logs --tail=100 dockdash dockdash-worker
curl --fail http://127.0.0.1:9999/health
df -h data
stat -c '%a %U:%G %n' data data/dockdash.db data/pki data/pki/controller.key 2>/dev/null
```

Before sharing logs, review them for hostnames, internal addresses, repository
URLs, webhook URLs, and other environment-specific data.

See [Operations](OPERATIONS.md) for enrollment, backup, rotation, upgrade, and
rollback, and [Security](SECURITY.md) for controls that must not be bypassed.
