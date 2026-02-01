# 🐳 DockerMinder

A Docker containerized web application for managing Docker containers on a host. View container status, manage containers (start/stop/restart), and maintain a shared URL bookmark list accessible across your network.

![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker)
![Python](https://img.shields.io/badge/Python-3.11-green?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey?logo=flask)

## ✨ Features

- **📊 Container Dashboard**: View all running containers with real-time status
- **🔌 Port Mapping**: See exposed ports with clickable LAN URLs
- **🎮 Container Control**: Start, stop, and restart containers from the web UI
- **🔐 Secure Login**: Password-protected access (default: admin/dockerminder)
- **🔗 URL Share**: Shared bookmark system for team URLs and services
- **📱 Responsive Design**: Works on desktop, tablet, and mobile
- **🌐 LAN Accessible**: Access from any device on your network

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose installed on your host

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/dockerminder.git
   cd dockerminder
   ```

2. **Start DockerMinder**
   ```bash
   docker-compose up -d
   ```

3. **Access the Web UI**
   
   Open your browser and navigate to:
   ```
   http://localhost:8080
   ```
   
   Or from another device on your network:
   ```
   http://<host-ip>:8080
   ```

4. **Login**
   - **Username**: `admin`
   - **Password**: `dockerminder`

   > ⚠️ **Important**: Change the default password after first login!

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Flask secret key for sessions |
| `DEFAULT_USERNAME` | `admin` | Default admin username |
| `DEFAULT_PASSWORD` | `dockerminder` | Default admin password |

### Custom Configuration

Create a `.env` file in the project root:

```env
SECRET_KEY=your-super-secret-key-here
DEFAULT_USERNAME=admin
DEFAULT_PASSWORD=your-secure-password
```

### Change the Port

Edit `docker-compose.yml` to change the exposed port:

```yaml
ports:
  - "3000:5000"  # Access on port 3000 instead of 8080
```

## 📖 Usage

### Dashboard

The dashboard displays all Docker containers on the host:

- **Green badge**: Container is running
- **Red badge**: Container is stopped/exited
- **Port links**: Click to open the service in a new tab

**Actions available:**
- 🔄 **Restart**: Restart a running container
- ⏹️ **Stop**: Stop a running container
- ▶️ **Start**: Start a stopped container

### URL Share

A shared bookmark system for your team:

1. Click **"URL Share"** in the navigation
2. Click **"Add URL"** to add a new bookmark
3. Organize URLs by category
4. Access shared URLs from any device

### Change Password

1. Click **"Settings"** in the navigation
2. Enter your current password
3. Set a new password (minimum 6 characters)
4. Click **"Change Password"**

## 🔒 Security Considerations

1. **Change default credentials immediately** after first login
2. **Use a strong SECRET_KEY** in production
3. **Limit network access** - only expose to trusted networks
4. Consider placing behind a **reverse proxy with HTTPS**

## 🏗️ Architecture

```
dockerminder/
├── app.py              # Flask application
├── Dockerfile          # Container build instructions
├── docker-compose.yml  # Container orchestration
├── requirements.txt    # Python dependencies
├── templates/          # Jinja2 HTML templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── urls.html
│   ├── add_url.html
│   ├── edit_url.html
│   └── change_password.html
└── static/
    ├── css/
    │   └── style.css   # Application styles
    └── js/
        └── app.js      # Client-side JavaScript
```

## 🛠️ Development

### Run Locally (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

### Build Docker Image

```bash
docker build -t dockerminder .
```

### Run with Docker

```bash
docker run -d \
  --name dockerminder \
  -p 8080:5000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  dockerminder
```

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/containers` | List all containers |
| POST | `/api/container/<id>/start` | Start a container |
| POST | `/api/container/<id>/stop` | Stop a container |
| POST | `/api/container/<id>/restart` | Restart a container |
| GET | `/api/urls` | List all shared URLs |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Docker SDK for Python](https://docker-py.readthedocs.io/) - Docker API integration
- [Flask-Login](https://flask-login.readthedocs.io/) - User session management

---

Made with ❤️ for Docker enthusiasts
