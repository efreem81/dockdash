# ⛵ DockDash

**Smooth sailing for your containers!**

A sleek, feature-rich container management dashboard with a nautical theme. Works with both **Docker** and **Podman**! Monitor containers, manage images, receive alerts via webhooks, scan for vulnerabilities, and more.

![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)
![Python](https://img.shields.io/badge/Python-3.11-green?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey?logo=flask)

## ✨ Features

### Container Management
- **📊 Dashboard**: View all containers with status, search, sort, and pagination
- **🎮 Container Control**: Start, stop, restart, and remove containers
- **🔃 Recreate Containers**: Pull latest image and recreate with same config
- **📜 Logs Viewer**: Real-time container logs with tail and auto-follow
- **💻 Execute Commands**: Run commands inside containers (exec)
- **🔍 Inspect Details**: View environment variables, mounts, networks, and labels
- **📈 Live Stats**: Real-time CPU and memory usage per container
- **💚 Health Checks**: Visual health status indicators for containers with health checks
- **📦 Compose Grouping**: Containers grouped by Docker Compose project

### Docker Fleet & Compose Deployments
- **🖥️ Multi-host Docker**: Manage unlimited Docker hosts through mTLS-authenticated DockDash agents
- **📦 Compose Orchestration**: Discover and adopt existing Compose projects from their owning directories
- **🚀 Safe Deployments**: Validate, pull, deploy, start, stop, restart, and scale Compose projects
- **🧭 Deployment Sources**: Adopt host projects or create Git-backed and DockDash-managed deployments
- **🩺 Deployment Checks**: Required-mount, capacity, Docker health, and optional HTTP application checks
- **🕰️ Revision Evidence**: Record configuration digests, image IDs, and durable operation history for rollback assistance

### Image Management
- **⬆️ Update Checking**: Check if container images have updates available
- **🧹 Cleanup Tools**: Remove dangling images, unused images, and stopped containers
- **🛡️ Vulnerability Scanning**: Scan images for CVEs using Trivy (optional)

### Monitoring & Alerts
- **📡 Background Monitoring**: Automatic container state and resource monitoring
- **🔔 Webhook Notifications**: Alerts via Discord, Slack, Telegram, or custom webhooks
- **⚠️ Threshold Alerts**: Get notified when CPU/memory exceeds thresholds
- **🚨 State Change Alerts**: Notifications for container start/stop/health changes

### Networking & Access
- **🔗 Smart Links**: Auto-detects HTTP vs HTTPS for exposed ports
- **🌐 LAN Accessible**: Access from any device on your network
- **📱 Responsive Design**: Works on desktop, tablet, and mobile

### Security & Sharing
- **🔐 Secure Login**: Password-protected access with CSRF protection
- **🔗 URL Share**: Shared bookmark system for team URLs and services
- **🍪 Secure Cookies**: Configurable session security for LAN or HTTPS

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose (or Podman and podman-compose) installed on your host

### Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:efreem81/dockdash.git
   cd dockdash
   ```

2. **Start DockDash**
   ```bash
   ./deploy.sh
   ```

   Helpful options:
   ```bash
   ./deploy.sh --quick   # restart without rebuilding
   ./deploy.sh --logs    # show recent logs after starting
   ```

3. **Access the Web UI**

   Open your browser and navigate to:
   ```
   http://localhost:9999
   ```

   Or from another device on your network:
   ```
   http://<host-ip>:9999
   ```

4. **Login**

   Set a unique `DEFAULT_PASSWORD` in `.env` before the first deployment. The
   deployment script refuses blank and known default passwords. The initial
   username defaults to `admin`.

### Using with Podman

DockDash works with Podman! For **rootless Podman**:

```bash
# Edit docker-compose.yml to use Podman socket
sed -i 's|/var/run/docker.sock|/run/user/1000/podman/podman.sock|' docker-compose.yml

# Start with podman-compose
podman-compose up -d
```

For **rootful Podman**, enable the Docker-compatible socket:

```bash
sudo systemctl enable --now podman.socket
# Then use docker-compose as normal
```

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | required/generated | Flask secret key for sessions |
| `DEFAULT_USERNAME` | `admin` | Default admin username |
| `DEFAULT_PASSWORD` | required | Initial admin password; blank and known defaults are rejected |
| `DOCKDASH_PORT` | `9999` | Host port to expose DockDash on |
| `HOST_IP` | (auto-detected) | LAN IP used for container link generation |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker/Podman socket path |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when running behind HTTPS |
| `SESSION_LIFETIME_HOURS` | `12` | Session lifetime in hours |
| `AUTO_START_MONITORING` | `0` | Set to `1` to auto-start background monitoring |

### Custom Configuration

Create a `.env` file in the project root:

```env
SECRET_KEY=your-super-secret-key-here
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=your-secure-password
DOCKDASH_PORT=9999
HOST_IP=192.168.1.50
AUTO_START_MONITORING=1
# If behind HTTPS (reverse proxy), enable secure cookies
# SESSION_COOKIE_SECURE=1
```

### Secure Docker fleet setup

Fleet agents are separate from the web controller. They never expose the
Docker socket directly and accept only mutually authenticated TLS connections.
Private keys and certificates are ignored by Git and must remain outside the
repository.

1. Create the private controller bridge and controller CA/client identity:

   ```bash
   docker network create dockdash-control
   sudo install -d -m 0700 /etc/dockdash-pki
   sudo agent/scripts/create-ca-controller.sh /etc/dockdash-pki
   install -d -m 0700 data/pki
   sudo install -m 0444 /etc/dockdash-pki/ca.crt data/pki/ca.crt
   sudo install -m 0444 /etc/dockdash-pki/controller.crt data/pki/controller.crt
   sudo install -m 0400 /etc/dockdash-pki/controller.key data/pki/controller.key
   ```

   Keep `/etc/dockdash-pki/ca.key` root-only and offline except while signing
   or rotating certificates. Never copy it to an agent.

2. On each agent host, generate its private key and CSR locally:

   ```bash
   sudo install -d -m 0700 /etc/dockdash-agent
   sudo agent/scripts/create-server-csr.sh /etc/dockdash-agent HOSTNAME
   ```

3. Transfer only `server.csr` to the CA host, review its subject, and sign it
   with the host's exact management IP or DNS name:

   ```bash
   sudo agent/scripts/sign-server-csr.sh /etc/dockdash-pki server.csr server.crt IP:192.0.2.10
   ```

   Return only `server.crt` and `ca.crt` to `/etc/dockdash-agent`. The agent's
   `server.key` never leaves that host. Verify `sslserver` and `sslclient`
   purposes with `openssl verify` before deployment.

4. Deploy `agent/compose.controller.yaml` on the controller host or
   `agent/compose.yaml`/`agent/compose.opt-only.yaml` on a remote host. Remote
   deployments require `DOCKDASH_AGENT_BIND` to be the exact management IP.

5. Before exposing TCP/9002, add a persistent host-forwarding rule that permits
   only the DockDash controller address, followed by a drop for other sources.
   Docker-published ports traverse `DOCKER-USER`, not the normal INPUT/UFW
   policy. Preserve `RELATED,ESTABLISHED` traffic before the drop, verify from
   both an allowed and denied source, and confirm container egress afterward.

6. Add the endpoint in **Fleet**, test it, and run **Discover / adopt**. The
   certificate SAN must match the URL exactly. Plain HTTP, URL credentials and
   redirect-based fallback are rejected.

Certificates are issued for 397 days by the included scripts. Rotate them
before expiry by generating a new local key/CSR and deploying the signed leaf
certificate during a controlled agent restart. Revocation is performed by
removing trust or issuing a replacement CA/controller identity; the agent does
not use an online CRL or OCSP responder. Back up the CA and controller identity
encrypted and separately from the managed hosts.

The `dockdash-worker` service serializes Compose mutations, rejects an accidental
second worker through a shared OS lock, and recovers an interrupted `running` job
back into the queue after restart.

### Vulnerability Scanning

DockDash bundles a commit-pinned Trivy binary in its controller image. Access
image scanning through **Settings → Vulnerability Scanning**.

## 📖 Usage

### Dashboard

The dashboard displays all Docker containers on the host:

| Badge | Meaning |
|-------|---------|
| 🟢 **running** | Container is running |
| 🔴 **exited** | Container has stopped |
| 💚 | Health check: healthy |
| ❤️ | Health check: unhealthy |
| ⬆️ | Image update available |

**Container Actions:**
| Button | Action |
|--------|--------|
| 🔄 | Restart container |
| ⏹️ | Stop container |
| ▶️ | Start container |
| 🗑️ | Remove container |
| 📊 | Toggle live stats |
| 💻 | Execute command |
| 📜 | View logs |
| 🔍 | Inspect details |
| 🔃 | Recreate (pull latest & restart) |

### Settings

Access **Settings** from the navigation to configure:

- **🔔 Webhooks**: Add Discord, Slack, Telegram, or custom webhook notifications
- **📡 Monitoring**: Start/stop background container monitoring
- **🛡️ Vulnerability Scanner**: Scan images for security vulnerabilities
- **🧹 Cleanup**: Remove unused images and stopped containers
- **🔑 Password**: Change your login password

### URL Share

A shared bookmark system for your team:

1. Click **"URL Share"** in the navigation
2. Click **"Add URL"** to add a new bookmark
3. Organize URLs by category
4. Access shared URLs from any device

## 🔒 Security Considerations

1. **Change default credentials immediately** after first login
2. **Use a strong SECRET_KEY** in production
3. **Limit network access** - only expose to trusted networks
4. Consider placing behind a **reverse proxy with HTTPS**
5. Set `SESSION_COOKIE_SECURE=1` when using HTTPS

DockDash includes CSRF protection and secure cookie defaults.

## 🏗️ Architecture

DockDash uses a modular Flask architecture with blueprints:

```
dockdash/
├── app.py                  # Application entry point
├── config.py               # App factory and configuration
├── models.py               # SQLAlchemy database models
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── requirements.txt
│
├── routes/                 # Flask blueprints (API endpoints)
│   ├── auth.py             # Authentication routes
│   ├── dashboard.py        # Dashboard views
│   ├── containers.py       # Container management API
│   ├── images.py           # Image management API
│   ├── urls.py             # URL sharing routes
│   ├── notifications.py    # Webhook management API
│   ├── monitoring.py       # Background monitoring API
│   └── vulnerabilities.py  # Vulnerability scanning API
│
├── services/               # Business logic layer
│   ├── docker_service.py   # Docker SDK operations
│   ├── image_service.py    # Image management logic
│   ├── lifecycle_service.py # Container recreate logic
│   ├── notification_service.py # Webhook sending
│   ├── scheduler_service.py # Background monitoring
│   └── vulnerability_service.py # Trivy integration
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── settings.html
│   ├── urls.html
│   ├── add_url.html
│   ├── edit_url.html
│   └── change_password.html
│
└── static/
    ├── logo.svg
    ├── css/
    │   └── style.css
    └── js/
        ├── app.js          # Shared utilities
        ├── dashboard.js    # Dashboard functionality
        └── settings.js     # Settings page functionality
```

## 🛠️ Development

### Run Locally (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Required on first startup; never use these example values in production.
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export DEFAULT_PASSWORD="choose-a-unique-password"

# Initialize database
python init_db.py

# Run the application
python app.py
```

### Build Docker Image

```bash
docker build -t dockdash .
```

### Run with Docker

```bash
docker run -d \
  --name dockdash \
  -p 9999:5000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v dockdash-data:/app/data \
  dockdash
```

## 📝 API Endpoints

### Containers
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/containers` | List all containers |
| GET | `/api/container/<id>` | Get container details |
| GET | `/api/container/<id>/stats` | Get container stats |
| GET | `/api/container/<id>/logs` | Fetch container logs |
| POST | `/api/container/<id>/start` | Start a container |
| POST | `/api/container/<id>/stop` | Stop a container |
| POST | `/api/container/<id>/restart` | Restart a container |
| POST | `/api/container/<id>/remove` | Remove a container |
| POST | `/api/container/<id>/exec` | Execute command |
| POST | `/api/container/<id>/recreate` | Recreate container |

### Images
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/images` | List all images |
| GET | `/api/image/check-update` | Check single image for updates |
| POST | `/api/images/check-updates` | Batch check for updates |
| POST | `/api/images/cleanup` | Clean up images |
| POST | `/api/containers/prune` | Prune stopped containers |

### Webhooks & Monitoring
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/webhooks` | List webhooks |
| POST | `/api/webhook` | Create webhook |
| PUT | `/api/webhook/<id>` | Update webhook |
| DELETE | `/api/webhook/<id>` | Delete webhook |
| POST | `/api/webhook/<id>/test` | Test webhook |
| GET | `/api/monitoring/status` | Get monitoring status |
| POST | `/api/monitoring/start` | Start monitoring |
| POST | `/api/monitoring/stop` | Stop monitoring |

### Vulnerability Scanning
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vulnerabilities/status` | Check Trivy availability |
| GET | `/api/vulnerabilities/scan?image=<ref>` | Scan single image |
| POST | `/api/vulnerabilities/scan` | Batch scan images |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/link/probe` | Probe HTTP/HTTPS for host:port |
| GET | `/api/urls` | List shared URLs |
| GET | `/health` | Health check endpoint |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Docker SDK for Python](https://docker-py.readthedocs.io/) - Docker API integration
- [Flask-Login](https://flask-login.readthedocs.io/) - User session management
- [Trivy](https://trivy.dev/) - Vulnerability scanner
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM

---

⛵ **DockDash** - Smooth sailing for your containers!
