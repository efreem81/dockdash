# Docker fleet operations

This runbook covers controller deployment, secure agent enrollment, project
adoption, controlled lifecycle operations, backup, certificate rotation, and
recovery. Commands assume Docker Compose v2.

## Controller deployment

1. Clone the repository and create `.env` from `.env.example`.
2. Set a unique `DEFAULT_PASSWORD` for first-user creation and a generated
   `SECRET_KEY`. Set secure-cookie variables when the UI is behind HTTPS.
3. Create the private controller network:

   ```bash
   docker network create dockdash-control
   ```

4. Create the controller CA/client identity as described below.
5. Validate and start the controller and worker:

   ```bash
   SECRET_KEY=validation DEFAULT_PASSWORD=validation docker compose config --quiet
   ./deploy.sh
   docker compose ps
   curl --fail http://127.0.0.1:9999/health
   ```

`./deploy.sh` pulls the current Git branch when the checkout has a remote, builds
without cache, and starts the services. `./deploy.sh --quick` does not rebuild;
do not use it when source, dependencies, entrypoints, or the image changed.

After deployment, confirm the image contains the intended revision. A healthy
container alone does not prove the expected code is running.

## Create the private PKI

Create the CA and controller client identity once on the CA host:

```bash
sudo install -d -m 0700 /etc/dockdash-pki
sudo agent/scripts/create-ca-controller.sh /etc/dockdash-pki
install -d -m 0700 data/pki
sudo install -m 0444 /etc/dockdash-pki/ca.crt data/pki/ca.crt
sudo install -m 0444 /etc/dockdash-pki/controller.crt data/pki/controller.crt
sudo install -m 0400 /etc/dockdash-pki/controller.key data/pki/controller.key
```

Move the CA private key to encrypted offline storage when enrollment is
complete. Never place it on an agent.

## Enroll an agent host

Generate the server key and CSR on the agent host:

```bash
sudo install -d -m 0700 /etc/dockdash-agent
sudo agent/scripts/create-server-csr.sh /etc/dockdash-agent HOSTNAME
```

Transfer only `server.csr` to the CA host. Review and sign it with the exact
management identity used by the controller:

```bash
sudo agent/scripts/sign-server-csr.sh \
  /etc/dockdash-pki server.csr server.crt IP:192.0.2.10
```

Return `server.crt` and `ca.crt` to `/etc/dockdash-agent`. Do not transfer
`server.key` off-host. Verify purposes and the SAN before starting:

```bash
openssl verify -CAfile ca.crt -purpose sslserver server.crt
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName
```

Choose the Compose definition:

| Host type | Definition |
|---|---|
| Controller host | `agent/compose.controller.yaml` |
| Host with recorded Compose and `/opt` roots | `agent/compose.yaml` |
| Managed `/opt` deployments only | `agent/compose.opt-only.yaml` |

Review every mounted and configured root. A read-only host path is still visible
to a process with Docker control, so expose only what discovery and Compose
resolution require.

For a remote host, set `DOCKDASH_AGENT_BIND` to its exact management address and
install a persistent forwarding policy that permits TCP/9002 only from the
controller. Then build and start from a dedicated directory such as
`/opt/dockdash-agent`:

```bash
DOCKDASH_AGENT_BIND=192.0.2.10 docker compose config --quiet
DOCKDASH_AGENT_BIND=192.0.2.10 docker compose up -d --build
docker compose ps
```

Do not expose a controller-host agent port. Its Compose definition connects it
only to `dockdash-control`.

## Agent acceptance

From the controller runtime, require an authenticated response:

```bash
docker compose exec dockdash-worker python -c \
  "import requests; print(requests.get(
  'https://AGENT_NAME:9002/health',
  cert=('/app/data/pki/controller.crt','/app/data/pki/controller.key'),
  verify='/app/data/pki/ca.crt', timeout=5).status_code)"
```

Also prove that a request without a client certificate fails and that a
non-controller source cannot connect. Inspect the running container:

```bash
docker inspect dockdash-agent --format \
  'readonly={{.HostConfig.ReadonlyRootfs}} caps={{json .HostConfig.CapDrop}} security={{json .HostConfig.SecurityOpt}}'
```

Expected: `readonly=true`, `caps=["ALL"]`, and
`no-new-privileges:true`.

## Register and discover

In **Fleet**, add an agent endpoint whose HTTPS hostname/IP exactly matches the
certificate SAN. Test it before continuing. Then select the endpoint and use
**Projects → Discover / adopt**.

The CLI offers the same administrative path:

```bash
docker compose exec dockdash python dockdash_cli.py endpoint-list
docker compose exec dockdash python dockdash_cli.py endpoint-test --name HOST
docker compose exec dockdash python dockdash_cli.py project-sync --endpoint HOST
```

Review discoveries before running actions. A discovered directory is not proof
that its data mounts, dependencies, or application endpoint are healthy.

## Configure project safety checks

For each important project:

- add storage dependencies as required mountpoints;
- add an HTTP/HTTPS application health URL when practical;
- retain default 200–399 success unless a specific status is intentionally
  healthy; and
- use a timeout long enough for migrations or cold storage startup.

Then run **Validate**. Validation checks path authorization, free capacity,
required mounts, and Compose configuration without changing the workload.

## Lifecycle and deployment actions

| Action | Behavior |
|---|---|
| Validate | Run preflight and Compose configuration validation |
| Start | Start selected services without creating absent containers |
| Stop | Stop selected running services |
| Restart | Restart selected running services |
| Pull | Pull images for selected services |
| Up | Pull, run `up -d --wait`, then run the application check |
| Recreate | Pull, force-recreate, wait, then run the application check |
| Logs | Return bounded Compose logs |
| Scale | Apply bounded service replicas and wait for health |
| Down | Remove project containers/networks and orphans, never volumes |

If no services are selected, start-like actions derive only currently running
services. This prevents an operation from silently starting intentionally
stopped services.

Watch the durable job record until it reaches `succeeded` or `failed`. Read the
captured output and post-action health result; do not treat a submitted or
`running` job as completion.

Image deletion and cleanup are immediate endpoint actions rather than Compose
jobs. Unused-volume prune removes every volume Docker considers unused on the
selected host. Inventory and back up candidate volumes before invoking it; never
use it as a generic disk-space or troubleshooting step.

## Backup

Back up three separate layers:

1. Controller SQLite database using SQLite's online backup API, or with the
   controller and worker stopped.
2. Controller certificate/key set and CA material, encrypted and separate from
   managed hosts.
3. Each workload's Compose definition, environment/secret source, and
   application data through its owning backup procedure.

The DockDash database is not a backup of application data or adopted Compose
files. Copying a live SQLite file with ordinary `cp` can produce an inconsistent
backup when WAL mode is active.

## Certificate rotation

1. Generate a new key and CSR on the affected host.
2. Sign it with the same exact SAN and verify `sslserver` purpose.
3. Stage the new leaf and CA files with restrictive permissions.
4. Restart only that agent during a controlled window.
5. Re-run authenticated, unauthenticated, network-source, and runtime-hardening
   checks.
6. Remove the superseded private key after rollback time expires.

Rotate the controller identity similarly, but update the controller PKI mount
and verify every agent. A CA rotation requires coordinated trust deployment.

## Upgrade and rollback

Before upgrading:

```bash
git status --short
pre-commit run --all-files
docker compose config --quiet
```

Record the current Git commit, controller and agent image IDs, database backup,
and certificate expiry. Build the agent and controller from the same reviewed
revision. Upgrade one remote agent first, verify it, then continue host by host.
Upgrade the controller/worker last unless the release explicitly requires the
opposite order.

For rollback, use the recorded image/source revision and database backup. Never
remove volumes merely to force a clean start. Confirm schema compatibility before
running an older controller against a newer database.

## Decommission an endpoint

1. Stop scheduling work and let active jobs finish.
2. Disable the endpoint in DockDash.
3. Remove the agent only from its exact Compose directory.
4. Remove the exact TCP/9002 forwarding rules for that host.
5. Revoke or securely destroy the retired server identity.
6. Preserve workload Compose files and data; agent removal must not remove them.
7. Update operational documentation and the change record.

See [Troubleshooting](TROUBLESHOOTING.md) when an acceptance or lifecycle check
fails.
