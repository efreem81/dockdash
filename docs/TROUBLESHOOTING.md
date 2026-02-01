# DockDash Troubleshooting Guide

## Common Issues & Solutions

### Database Initialization Errors

#### Error: `sqlite3.OperationalError: unable to open database file`

**Cause:** The `data/` directory doesn't exist or isn't writable when the application starts.

**Solutions:**

1. **Ensure the volume is properly mounted (docker-compose)**
   ```yaml
   volumes:
     - dockdash_data:/app/data
   ```

2. **Rebuild the Docker image**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up
   ```

3. **Check volume permissions**
   ```bash
   docker volume ls
   docker volume inspect dockdash_data
   ```

4. **Run database initialization manually**
   ```bash
   docker-compose exec dockdash python init_db.py
   ```

5. **Verify the data directory exists**
   ```bash
   docker-compose exec dockdash ls -la /app/data/
   ```

**Prevention:**
- The Dockerfile now creates the `data/` directory automatically
- The startup script (`init_db.py`) runs before Gunicorn starts
- Database initialization is also deferred to the first request as a fallback

---

### Connection Errors to Docker/Podman

#### Error: `docker.errors.DockerException: Error while fetching server API version`

**Cause:** The Docker/Podman socket isn't mounted or accessible.

**Solutions:**

**For Docker:**
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

**For Podman (rootless):**
```yaml
volumes:
  - /run/user/1000/podman/podman.sock:/var/run/docker.sock
```

**For Podman (rootful):**
```yaml
volumes:
  - /run/podman/podman.sock:/var/run/docker.sock
```

**Verify the socket exists:**
```bash
# Docker
ls -l /var/run/docker.sock

# Podman (rootless)
ls -l /run/user/1000/podman/podman.sock

# Podman (rootful)
ls -l /run/podman/podman.sock
```

---

### Login Issues

#### Error: Invalid username or password

**Default credentials:**
```
Username: admin
Password: dockdash
```

**Reset default credentials:**

Option 1: Delete the database and restart
```bash
docker volume rm dockdash_data
docker-compose down
docker-compose up
```

Option 2: Change environment variables
```bash
# In docker-compose.yml
environment:
  - DEFAULT_USERNAME=myuser
  - DEFAULT_PASSWORD=mypassword
```

Then reset:
```bash
docker-compose down
docker-compose up
```

Option 3: SQL query (advanced)
```bash
docker-compose exec dockdash python -c "
from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    user = User.query.filter_by(username='admin').first()
    if user:
        user.password_hash = generate_password_hash('newpassword')
        db.session.commit()
        print('Password reset')
    else:
        print('User not found')
"
```

---

### Container Management Issues

#### Error: No containers showing up

**Solutions:**

1. **Verify Docker socket is mounted**
   ```bash
   docker-compose exec dockdash python -c "
   import docker
   client = docker.from_env()
   containers = client.containers.list()
   print(f'Found {len(containers)} containers')
   "
   ```

2. **Check if containers exist**
   ```bash
   docker ps -a
   ```

3. **Verify Docker daemon is running**
   ```bash
   docker ps
   ```

4. **Restart the container**
   ```bash
   docker-compose restart dockdash
   ```

---

#### Error: Cannot connect to container ports

**Cause:** Container port mapping not configured in DockDash.

**Solution:** Make sure containers have port mappings:
```bash
docker ps --format "table {{.Names}}\t{{.Ports}}"
```

DockDash detects ports from:
- Container's exposed ports
- Port bindings in docker-compose
- Port mappings in docker run

---

### URL Sharing Issues

#### URLs not saving

**Solutions:**

1. **Check database connectivity**
   ```bash
   docker-compose logs dockdash | grep -i "database\|error"
   ```

2. **Verify database permissions**
   ```bash
   docker-compose exec dockdash ls -la /app/data/dockdash.db
   ```

3. **Check free disk space**
   ```bash
   docker exec dockdash df -h /app/data
   ```

4. **Reset the database**
   ```bash
   docker volume rm dockdash_data
   docker-compose restart dockdash
   ```

---

### Performance Issues

#### Application is slow or unresponsive

**Solutions:**

1. **Check container resources**
   ```bash
   docker stats dockdash
   ```

2. **Increase worker processes** (edit docker-compose.yml)
   ```yaml
   environment:
     - WORKERS=4
   ```
   Then rebuild and restart.

3. **Check logs for errors**
   ```bash
   docker-compose logs -f dockdash
   ```

4. **Restart the container**
   ```bash
   docker-compose restart dockdash
   ```

5. **Increase Docker resources**
   - macOS/Windows: Docker Desktop > Preferences > Resources
   - Linux: Check available system memory

---

#### Many containers showing slow page load

**Solution:** Enable caching headers in nginx or reverse proxy:
```nginx
location / {
    proxy_pass http://dockdash:5000;
    proxy_cache_valid 200 1m;  # Cache successful responses for 1 minute
    proxy_cache_key "$scheme$request_method$host$request_uri";
}
```

---

### Port Conflicts

#### Error: Port 8080 already in use

**Solution 1: Change the port** (docker-compose.yml)
```yaml
ports:
  - "9000:5000"  # Use 9000 instead of 8080
```

**Solution 2: Find and stop the conflicting service**
```bash
lsof -i :8080  # Find what's using port 8080
```

---

### Docker Compose Issues

#### Error: Cannot connect to Docker daemon

**Solution:**
```bash
# Ensure Docker daemon is running
docker version

# Check Docker socket
ls -l /var/run/docker.sock
```

#### Volume not persisting data

**Solution:**
```bash
# List volumes
docker volume ls

# Inspect the volume
docker volume inspect dockdash_data

# Check mount point
docker-compose inspect dockdash | grep -A 5 "Mounts"
```

---

### SSL/HTTPS Issues

#### Error: Connection not secure / Certificate errors

**Solution:** Set up a reverse proxy with SSL:

**Using nginx:**
```nginx
upstream dockdash {
    server localhost:9999;
}

server {
    listen 443 ssl http2;
    server_name dockdash.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://dockdash;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name dockdash.example.com;
    return 301 https://$server_name$request_uri;
}
```

**Using Traefik (recommended for Docker):**
```yaml
services:
  dockdash:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dockdash.rule=Host(`dockdash.example.com`)"
      - "traefik.http.routers.dockdash.entrypoints=websecure"
      - "traefik.http.routers.dockdash.tls.certresolver=letsencrypt"
      - "traefik.http.services.dockdash.loadbalancer.server.port=5000"
```

---

## Debugging

### Enable Debug Logging

**Check application logs:**
```bash
docker-compose logs -f dockdash
```

**Check Docker socket access:**
```bash
docker-compose exec dockdash python -c "
import docker
try:
    client = docker.from_env()
    containers = client.containers.list()
    print(f'Successfully connected. Found {len(containers)} containers')
except Exception as e:
    print(f'Error: {e}')
"
```

**Check database:**
```bash
docker-compose exec dockdash python -c "
from app import app, db, User, SharedURL
with app.app_context():
    print(f'Users: {User.query.count()}')
    print(f'URLs: {SharedURL.query.count()}')
"
```

### View Raw Database

```bash
# Enter the container
docker-compose exec dockdash bash

# Use sqlite3
sqlite3 /app/data/dockdash.db

# View tables
.tables

# View schema
.schema

# Query users
SELECT * FROM user;

# Exit
.quit
```

---

## Getting Help

### Collect Debug Information

```bash
#!/bin/bash
echo "=== Docker Version ==="
docker --version

echo "=== Docker Compose Version ==="
docker-compose --version

echo "=== DockDash Logs ==="
docker-compose logs dockdash | tail -50

echo "=== Container Status ==="
docker-compose ps

echo "=== Volume Status ==="
docker volume ls | grep dockdash

echo "=== Network Status ==="
docker network ls | grep dockdash

echo "=== Database Status ==="
docker-compose exec dockdash ls -lah /app/data/ 2>/dev/null || echo "Cannot access database directory"
```

Save this as `debug.sh` and run:
```bash
chmod +x debug.sh
./debug.sh > debug.log
```

Share the output when reporting issues.

---

## Prevention Checklist

- [ ] Use named volumes for persistent data
- [ ] Set appropriate resource limits
- [ ] Keep Docker/Podman and images updated
- [ ] Monitor disk space
- [ ] Regular backups of database
- [ ] Use HTTPS in production
- [ ] Enable rate limiting
- [ ] Strong SECRET_KEY configured
- [ ] Change default credentials
- [ ] Monitor logs for errors

---

**Last Updated:** February 1, 2026  
**For more help:** See [SECURITY.md](SECURITY.md) for production deployment guidance.
