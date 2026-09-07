# DockDash security model

This document describes the security contract implemented by the current
repository. It is not a claim that every deployment is running the current
commit; verify the deployed image before relying on a control.

## Trust boundary

DockDash is an authenticated Docker management application for trusted
administrators. It is not a multi-tenant isolation boundary and does not provide
RBAC. A DockDash administrator can perform actions that ultimately control a
Docker daemon.

Both the controller and every agent can access a Docker socket. Docker socket
access is effectively root-equivalent on that host. Container hardening reduces
the exposed attack surface but cannot make a compromised Docker-socket client
unprivileged. Restrict the UI and agent network paths accordingly.

## Implemented controls

### Controller and browser session

- Authentication is required for management pages and APIs.
- Passwords are stored with Werkzeug password hashing.
- Flask-WTF CSRF protection covers state-changing browser requests.
- `SECRET_KEY` is mandatory outside tests. The application fails closed when it
  is absent.
- `DEFAULT_PASSWORD` is required only while creating the first user. Blank and
  known default values are rejected outside tests.
- Session and remember cookies are HTTP-only and SameSite `Lax` by default.
  Set `SESSION_COOKIE_SECURE=1` and `REMEMBER_COOKIE_SECURE=1` behind HTTPS.
- Startup fails if database initialization or a required schema migration fails.
  `/health` reports HTTP 503 if Docker or the complete database schema is not
  available.
- The default SQLite directory is mode `0700`; the database, WAL, and SHM files
  are mode `0600`. The controller and worker retain a `077` umask.
- Request logging records route metadata and JSON key names, not request bodies
  for login or password routes.

The controller does not terminate public TLS itself. Put it behind an HTTPS
reverse proxy, restrict it to trusted management clients, and enable secure
cookies. Do not publish TCP/9999 directly to the internet.

### Agent transport

Agents are HTTPS-only and require mutual TLS:

- TLS 1.2 is the minimum; TLS 1.3 is supported.
- The agent requires a client certificate signed by the configured private CA.
- The controller verifies the agent certificate chain and hostname/IP SAN.
- Agent URLs must use `https://`, cannot contain credentials, and are called
  with redirects disabled.
- There is no plaintext, certificate-less, or verification-disabled fallback.
- The CA identity, controller client identity, and server identities have
  distinct extended key usages.

The supplied certificate scripts issue 397-day leaves. Record their expiration
in monitoring and rotate them before expiry. The agent does not implement CRL or
OCSP checking; revoke an identity by removing trust, replacing the CA, or
reissuing the affected controller/agent identities.

Certificate placement:

| Location | Files | Required handling |
|---|---|---|
| CA host | `ca.key`, `ca.crt` | Keep `ca.key` root-only and offline except while signing |
| Controller | `ca.crt`, `controller.crt`, `controller.key` | Directory `0700`; key `0400` |
| Agent host | `ca.crt`, `server.crt`, `server.key` | Generate `server.key` locally; never transfer it off-host |

Never commit certificates or keys. The repository ignores the standard PKI
paths, and pre-commit scans for private-key material.

### Agent runtime and network exposure

The provided agent Compose definitions:

- use a read-only root filesystem;
- drop all Linux capabilities;
- set `no-new-privileges`;
- provide small `noexec,nosuid` temporary filesystems;
- mount adopted Compose and runtime-data paths read-only;
- mount `/mnt` read-only for mountpoint preflight checks;
- allow writes only below the configured managed root (normally
  `/opt/dockdash-managed`); and
- bind remote TCP/9002 to the exact `DOCKDASH_AGENT_BIND` management address.

Docker-published ports traverse host forwarding rules. On a remote agent host,
install a persistent `DOCKER-USER` (or equivalent) policy that permits
established traffic and TCP/9002 only from the controller, then drops other
sources. Do not rely solely on UFW or the host INPUT chain. The controller-host
agent uses the private `dockdash-control` bridge and publishes no host port.

Verify after every Docker or firewall restart:

1. An mTLS request from the controller succeeds.
2. A request without a client certificate fails.
3. A connection from a non-controller source is denied.
4. The agent container remains read-only with all capabilities dropped.

### Operation boundary

The remote API is intentionally narrower than the Docker API:

- Remote container operations: inventory, details, stats, logs, start, stop,
  restart, and remove.
- Remote image operations: inventory, pull, delete, dangling-image prune, and
  unused-volume prune.
- Compose operations: discover, validate, start, stop, restart, pull, up,
  recreate, logs, scale, and down without volumes.
- Managed and Git-backed projects are confined below the managed root.
- Arbitrary host shell execution, remote container exec, a general filesystem
  API, full system prune, and `docker compose down -v` are not exposed by the
  agent.

Unused-volume prune is an intentionally exposed, destructive host-wide action.
Docker decides which volumes are unused. Confirm the selected endpoint, inventory
candidate volumes, and verify backups before invoking it.

Every path is canonicalized after symlink resolution and must stay within an
allowlisted root. Compose commands use fixed argument vectors with `shell=False`.
Project routes re-resolve the project within the explicitly selected endpoint,
and explicit invalid or disabled endpoint selections fail closed.

The controller sends authoritative project paths and health settings from its
database. User-supplied job options are filtered by action. The worker serializes
mutations with an OS lock, persists jobs before execution, recovers interrupted
`running` jobs to the queue, and marks malformed jobs failed without stalling
later work.

### Deployment data

Adopted Compose files remain on their owning hosts and are mounted read-only.
DockDash stores project metadata, configuration digests, job evidence, image
IDs, and revision metadata. It does not copy adopted Compose contents into the
controller database because Compose files can reference secrets.

Managed Git refreshes clone and validate in staging before atomic promotion.
Failed validation leaves the active checkout unchanged; the prior checkout is
retained below the managed backup tree.

## Production checklist

- [ ] Controller image was built from the intended Git commit.
- [ ] UI is behind HTTPS and reachable only by trusted administrators.
- [ ] Secure session and remember cookies are enabled.
- [ ] `.env` is mode `0600`; no example or default credentials remain.
- [ ] `data/` is `0700`; SQLite database/WAL/SHM files are `0600`.
- [ ] Controller PKI directory is `0700`; private key is `0400`.
- [ ] Each endpoint uses an HTTPS URL matching the certificate SAN.
- [ ] Remote listeners bind exact management addresses.
- [ ] Persistent forwarding policy allows agent traffic only from the controller.
- [ ] Authorized, unauthorized, and old-TLS agent tests have been run.
- [ ] Certificate expiry is monitored and encrypted backups exist.
- [ ] SQLite is backed up with its online backup API or while services are stopped.
- [ ] A restore has been tested without using `docker compose down -v`.
- [ ] `pre-commit run --all-files` passes for the deployed revision.

## Known limitations

- No RBAC or fine-grained authorization. This is an accepted scope decision for
  a single trusted administrator, not an isolation control.
- No built-in login rate limiting or security-header middleware. Enforce rate
  limits, HSTS, and related browser headers at the reverse proxy.
- Controller SQLite and webhook configuration are not encrypted at rest.
  Protect the host, file permissions, backups, and administrative access.
- Agent access to the Docker socket remains root-equivalent.
- Certificate revocation is operational rather than online.
- Remote container exec, full system prune, and `docker compose down -v` are
  deliberately absent. Unused-volume prune remains a high-impact administrator
  action.

## Validation gate

The repository gate runs formatting and secret checks, Ruff, Bandit, dependency
audits for the controller and agent, ShellCheck, controller and agent regression
tests, JavaScript syntax validation, Compose validation, clean image builds,
Trivy scanning for actionable High/Critical findings, and containerized mTLS
tests for authorized, unauthorized, TLS-version, and hardened-runtime behavior.

Run it before release:

```bash
pre-commit run --all-files
```

See [Architecture](ARCHITECTURE.md), [Operations](OPERATIONS.md), and
[Troubleshooting](TROUBLESHOOTING.md) for deployment and recovery procedures.
