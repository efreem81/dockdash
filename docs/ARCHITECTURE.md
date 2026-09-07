# Docker fleet architecture

DockDash provides one authenticated controller for multiple standalone Docker
hosts. It targets the container, image, Docker Compose, lifecycle, and deployment
use cases that this project previously depended on Portainer for. Kubernetes,
Swarm, RBAC, and team isolation are outside the current scope.

## Components

```text
Administrator browser
        |
        | HTTPS through the deployment's reverse proxy
        v
DockDash controller/UI ---- SQLite state and revision evidence
        |
        +---- durable single-worker job queue
        |
        | HTTPS + mutual TLS
        v
DockDash agent on each host ---- Docker socket
        |                         Docker Compose CLI
        +---- adopted projects (read-only definitions)
        +---- managed projects (allowlisted writable root)
```

| Component | Responsibility |
|---|---|
| Controller/UI | Authentication, endpoint selection, inventory views, project configuration, and job submission |
| Worker | Serialized Compose mutations, durable job status, recovery of interrupted work, and revision capture |
| Agent | Narrow Docker/Compose API, path enforcement, preflight checks, command execution, and application health checks |
| SQLite | Users, endpoint/project metadata, jobs, image state, and sanitized deployment revisions |
| Owning host | Canonical adopted Compose files, environment files, runtime data, Docker state, and managed deployment content |

The controller and worker share `data/` and the private `dockdash-control`
network. The controller-host agent is reachable only on that private bridge.
Remote agents bind TCP/9002 to an explicit management IP.

## Endpoint model

An endpoint represents exactly one Docker daemon. The Fleet page performs fresh
health requests and records both the check time and any error; it does not use a
manually entered state hint as evidence that a host is online. Each browser
request resolves an enabled endpoint from an explicit endpoint ID, request
header, query string, or the authenticated session. An explicitly invalid or
disabled endpoint fails closed. Projects are unique by endpoint and name, and
project routes verify both
identifiers before reading or mutating state.

Agent endpoints require an HTTPS URL without embedded credentials. The
controller uses one private CA trust bundle and a CA-signed client identity.
Each agent has a server certificate whose IP or DNS SAN matches its endpoint
URL.

## Inventory and lifecycle behavior

The dashboard can inventory containers and images from the selected endpoint.
Its **All Hosts** option queries every enabled endpoint with a bounded timeout,
shows inventory from each reachable host, labels every container with its
owner, and reports unavailable hosts separately. This consolidated view is
read-only; lifecycle and deployment controls require selecting the owning host.
For remote endpoints, the agent returns container details with likely secret
environment variables and labels redacted.

Update and vulnerability results are stored with endpoint scope. The same image
tag on two hosts cannot overwrite the other host's result. Update checks run on
the owning agent and compare that host's local digest with the allowlisted
registry. Trivy runs on the owning agent against the immutable local image ID,
not an arbitrary registry target.

Container inventory is annotated with its adopted Compose project, service, and
endpoint-specific capabilities. The UI uses that server-provided contract to
avoid presenting local-only exec/recreate controls on agents, hides deletion
for Compose-owned containers, and routes safe updates through the owning
project.

Container operations are immediate. Compose project mutations are queued:

```text
UI or CLI request
  -> validate endpoint/project ownership
  -> persist queued operation_job
  -> worker claims one job under an OS lock
  -> capture before state
  -> agent validates and runs an allowlisted Compose action
  -> optional application health check
  -> capture after state and deployment revision
  -> for update workflows, refresh registry and vulnerability evidence
  -> persist succeeded or failed result
```

Only one worker may hold the shared lock. After a process restart, jobs left in
`running` state are returned to the queue. An invalid job is marked failed, and
the worker continues to later jobs.

## Compose project sources

### Adopted

Discovery first reads Docker Compose ownership labels from live containers, then
scans configured roots to find stopped projects. Backup, archive, `.git`, data,
and similar trees are excluded. Adoption stores metadata and a configuration
digest; it does not rewrite or copy the Compose definition.

Adopted project trees and common `env_file` roots are mounted read-only. Symlink
targets must also resolve within an allowlisted, mounted root.

### Managed

The agent writes a supplied Compose definition below
`DOCKDASH_MANAGED_ROOT`. It writes to a temporary file, validates it with Docker
Compose, fsyncs it, and atomically replaces the active definition only after
validation succeeds.

### Git-backed

Git-backed projects are cloned into staging below the managed root. The requested
ref and Compose file are validated before atomic promotion. A failed clone or
validation does not alter the active checkout. The previous checkout is retained
in the managed backup tree for operator-assisted rollback.

Repository authentication is not stored in DockDash. Use a repository URL and
host credential mechanism appropriate for the deployment without embedding
secrets in URLs.

## Preflight and health checks

Before actions that can start workloads, the agent verifies:

- the working directory has at least `DOCKDASH_AGENT_MIN_FREE_BYTES` free
  (1 GiB by default);
- every configured required path is a real mountpoint;
- every project/config path remains inside an allowed root; and
- `docker compose config --quiet` succeeds.

`up` and `recreate` pull images before starting. Start-like actions can wait for
Docker Compose health and then poll an optional HTTP/HTTPS application URL. The
default accepted status range is 200–399; a project can declare exact intentional
statuses such as an authentication challenge. Health URLs may not contain
credentials.

## Revision and rollback evidence

A revision records the source revision when known, Compose configuration digest,
and the before/after image IDs and container state. Adopted Compose content is
not copied into SQLite. DockDash assists rollback decisions but does not claim
automatic data rollback: restoring an earlier image can still be incompatible
with application data migrations.

Rollback is therefore operator-controlled:

1. Read the failed job and revision evidence.
2. Confirm the owning host, Compose directory, mounts, and backup state.
3. Restore the prior managed checkout or pin the prior image reference.
4. Validate Compose and required mounts.
5. Redeploy and verify Docker and application health.

Never use `docker compose down -v` during recovery.

## Security boundaries

The agent is not a Docker API proxy. It exposes fixed resource/action routes and
constructs fixed argument arrays without invoking a shell. Remote exec, arbitrary
commands, full system prune, and volume-destructive Compose down are deliberately
unavailable. Unused-volume prune is exposed as an explicit host-wide cleanup
action and must be treated as destructive.

Agent security scans use a pinned Trivy build, fixed argument vectors, validated
image references, a local-image existence check, a 10-minute per-image timeout,
bounded JSON and finding counts, and a private cache in the ephemeral `/tmp`
tmpfs. Update requests are limited to explicitly allowlisted HTTPS registries
and bearer-token hosts to prevent arbitrary network probing.

See [Security](SECURITY.md) for the mTLS, network, filesystem, certificate, and
residual-risk contract.

## Persistence and availability

The controller currently uses one SQLite database and one active worker, so the
controller is not horizontally scalable. Agents and Docker workloads continue
running if the controller is unavailable, but new operations and central
inventory are unavailable until it returns.

Back up the SQLite database consistently, the controller PKI separately and
encrypted, and the CA key separately from managed hosts. Runtime application
data remains the responsibility of each Compose project.
