# DockDash Security Guide

## Overview

This document outlines security best practices, known vulnerabilities, and implementation guides for securing your DockDash installation.

---

## Current Security Status

⚠️ **WARNING:** DockDash currently has several security vulnerabilities that must be addressed before production deployment.

### Security Checklist

- [ ] CSRF protection enabled
- [ ] Rate limiting configured
- [ ] HTTPS enforced
- [ ] Session timeout configured
- [ ] Strong SECRET_KEY set
- [ ] Audit logging enabled
- [ ] Regular backups configured
- [ ] Security headers configured
- [ ] Input validation implemented
- [ ] SQL injection protection verified

---

## Quick Fixes (Do These Now)

### 1. Set Strong SECRET_KEY

```bash
# Generate a strong secret key
python -c 'import secrets; print(secrets.token_hex(32))'

# Set it in your environment
export SECRET_KEY="your-generated-key-here"
```

**In docker-compose.yml:**
```yaml
environment:
  - SECRET_KEY=${SECRET_KEY}  # Never hardcode!
```

### 2. Enable HTTPS

**Option A: Using nginx reverse proxy**
```nginx
server {
    listen 443 ssl http2;
    server_name dockdash.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:9999;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Option B: Using Traefik**
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.dockdash.rule=Host(`dockdash.example.com`)"
  - "traefik.http.routers.dockdash.tls=true"
  - "traefik.http.routers.dockdash.tls.certresolver=letsencrypt"
```

### 3. Restrict Network Access

**In docker-compose.yml:**
```yaml
ports:
  - "127.0.0.1:8080:5000"  # Only accessible from localhost
```

**Using firewall:**
```bash
# Only allow specific IPs
sudo ufw allow from 192.168.1.0/24 to any port 8080
```

---

## Implementing CSRF Protection

### Step 1: Install Flask-WTF

```bash
pip install flask-wtf
```

Add to `requirements.txt`:
```
flask-wtf==1.2.1
```

### Step 2: Update app.py

```python
from flask_wtf.csrf import CSRFProtect

# Add after app initialization
csrf = CSRFProtect(app)

# Configure CSRF
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No timeout
app.config['WTF_CSRF_SSL_STRICT'] = True  # Require HTTPS
```

### Step 3: Update Templates

**In base.html:**
```html
<head>
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
```

**In app.js:**
```javascript
// Add CSRF token to all AJAX requests
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

fetch('/api/container/abc123/restart', {
    method: 'POST',
    headers: {
        'X-CSRFToken': csrfToken
    }
});
```

**In forms:**
```html
<form method="POST">
    {{ csrf_token() }}
    <!-- form fields -->
</form>
```

---

## Implementing Rate Limiting

### Step 1: Install Flask-Limiter

```bash
pip install flask-limiter redis
```

### Step 2: Configure Rate Limiter

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    default_limits=["200 per day", "50 per hour"]
)
```

### Step 3: Apply Rate Limits

```python
@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    ...

@app.route('/api/container/<id>/restart', methods=['POST'])
@limiter.limit("10 per minute")
def restart_container(id):
    ...
```

### Step 4: Update docker-compose.yml

```yaml
services:
  dockdash:
    depends_on:
      - redis
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

---

## Implementing Audit Logging

### Step 1: Create Audit Log Model

```python
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(200))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='audit_logs')
```

### Step 2: Create Logging Decorator

```python
from functools import wraps

def audit_log(action):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)
            
            # Log the action
            log = AuditLog(
                user_id=current_user.id if current_user.is_authenticated else None,
                action=action,
                target=request.path,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string
            )
            db.session.add(log)
            db.session.commit()
            
            return result
        return decorated_function
    return decorator
```

### Step 3: Use the Decorator

```python
@app.route('/api/container/<container_id>/restart', methods=['POST'])
@login_required
@audit_log('container_restart')
def restart_container(container_id):
    ...
```

### Step 4: Create Audit Log Viewer

```python
@app.route('/admin/audit-logs')
@login_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('audit_logs.html', logs=logs)
```

---

## Session Security

### Configure Secure Sessions

```python
from datetime import timedelta

# Session configuration
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['SESSION_COOKIE_NAME'] = 'dockdash_session'

# Redis session storage (recommended)
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url('redis://localhost:6379')
```

### Implement Session Invalidation

```python
@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    # ... password change logic ...
    
    # Invalidate all other sessions
    session.clear()
    login_user(current_user)
    
    flash('Password changed. All other sessions have been logged out.', 'info')
```

---

## Security Headers

### Install Flask-Talisman

```bash
pip install flask-talisman
```

### Configure Security Headers

```python
from flask_talisman import Talisman

Talisman(app,
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",
        'style-src': "'self' 'unsafe-inline'",
        'img-src': "'self' data: https:",
        'font-src': "'self' data:",
    },
    content_security_policy_nonce_in=['script-src'],
    feature_policy={
        'geolocation': "'none'",
        'camera': "'none'",
        'microphone': "'none'"
    }
)
```

---

## Input Validation

### Install Marshmallow

```bash
pip install marshmallow
```

### Create Validation Schemas

```python
from marshmallow import Schema, fields, validate, ValidationError

class URLSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    url = fields.Url(required=True)
    description = fields.Str(validate=validate.Length(max=1000))
    category = fields.Str(validate=validate.Length(max=100))

class ContainerActionSchema(Schema):
    action = fields.Str(required=True, validate=validate.OneOf(['start', 'stop', 'restart']))
```

### Use Validation in Routes

```python
@app.route('/urls/add', methods=['POST'])
@login_required
def add_url():
    schema = URLSchema()
    
    try:
        data = schema.load(request.form)
    except ValidationError as err:
        flash(f'Validation error: {err.messages}', 'error')
        return redirect(url_for('add_url'))
    
    # Use validated data
    shared_url = SharedURL(**data, created_by=current_user.id)
    db.session.add(shared_url)
    db.session.commit()
```

---

## Docker Socket Security

### Problem: Mounting Docker Socket = Root Access

Mounting `/var/run/docker.sock` gives the container **full root access** to the host system.

### Solutions

#### Option 1: Use Docker Socket Proxy

```yaml
services:
  docker-proxy:
    image: tecnativa/docker-socket-proxy
    environment:
      CONTAINERS: 1
      IMAGES: 1
      INFO: 1
      NETWORKS: 0
      VOLUMES: 0
      POST: 1  # Allow start/stop/restart
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - docker-proxy
  
  dockdash:
    image: dockdash:latest
    environment:
      DOCKER_HOST: tcp://docker-proxy:2375
    networks:
      - docker-proxy
    ports:
      - "8080:5000"
```

#### Option 2: Use Rootless Podman

```bash
# Run DockDash with rootless Podman
podman run -d \
  -p 8080:5000 \
  -v $XDG_RUNTIME_DIR/podman/podman.sock:/var/run/docker.sock:ro \
  dockdash:latest
```

---

## Database Security

### Use PostgreSQL in Production

```yaml
services:
  dockdash:
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/dockdash
    depends_on:
      - postgres
  
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: dockdash
      POSTGRES_USER: dockdash
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### Encrypt Sensitive Data

```python
from cryptography.fernet import Fernet

# Generate key (store securely!)
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt API keys before storing
encrypted_key = cipher.encrypt(api_key.encode())

# Decrypt when needed
decrypted_key = cipher.decrypt(encrypted_key).decode()
```

---

## Backup Security

### Encrypt Backups

```bash
#!/bin/bash
# backup.sh

# Create backup
sqlite3 /app/data/dockdash.db ".backup '/tmp/backup.db'"

# Encrypt backup
gpg --encrypt --recipient your@email.com /tmp/backup.db

# Upload to secure storage
aws s3 cp /tmp/backup.db.gpg s3://your-bucket/backups/$(date +%Y%m%d).db.gpg

# Clean up
rm /tmp/backup.db /tmp/backup.db.gpg
```

### Automated Backup Service

```yaml
services:
  backup:
    image: offen/docker-volume-backup:latest
    environment:
      BACKUP_CRON_EXPRESSION: "0 2 * * *"  # Daily at 2 AM
      BACKUP_RETENTION_DAYS: 30
      AWS_S3_BUCKET_NAME: your-backup-bucket
      GPG_PASSPHRASE: ${BACKUP_ENCRYPTION_KEY}
    volumes:
      - dockdash_data:/backup/data:ro
```

---

## Security Monitoring

### Install Fail2Ban

```bash
# Install fail2ban
sudo apt install fail2ban

# Create DockDash jail
sudo nano /etc/fail2ban/jail.d/dockdash.conf
```

```ini
[dockdash]
enabled = true
port = 8080
filter = dockdash
logpath = /var/log/dockdash/access.log
maxretry = 5
bantime = 3600
```

### Log Failed Login Attempts

```python
@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        login_user(user)
        app.logger.info(f'Successful login: {username} from {request.remote_addr}')
        return redirect(url_for('dashboard'))
    else:
        app.logger.warning(f'Failed login attempt: {username} from {request.remote_addr}')
        flash('Invalid username or password', 'error')
```

---

## Security Testing

### Run Security Scan

```bash
# Install safety (checks for known vulnerabilities)
pip install safety

# Check dependencies
safety check

# Install bandit (static analysis)
pip install bandit

# Scan code for security issues
bandit -r /app -f json -o security-report.json
```

### Automated Security Testing

```yaml
# .github/workflows/security.yml
name: Security Scan

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
      - name: Run Bandit
        run: |
          pip install bandit
          bandit -r app.py -f json -o bandit-report.json
```

---

## Incident Response Plan

### If You Suspect a Breach

1. **Immediate Actions:**
   - Take DockDash offline
   - Change all passwords
   - Revoke all API keys
   - Check audit logs

2. **Investigation:**
   - Review recent container actions
   - Check for unauthorized users
   - Examine network traffic logs
   - Look for modified files

3. **Recovery:**
   - Restore from clean backup
   - Update all dependencies
   - Apply security patches
   - Re-deploy with hardened config

4. **Post-Incident:**
   - Document what happened
   - Update security procedures
   - Inform affected users
   - Implement additional monitoring

---

## Security Best Practices

### ✅ DO

- Use strong, unique passwords
- Enable HTTPS everywhere
- Keep software updated
- Use environment variables for secrets
- Implement rate limiting
- Enable audit logging
- Regular backups
- Use a firewall
- Monitor logs
- Use least privilege access

### ❌ DON'T

- Hardcode secrets in code
- Use default credentials
- Expose to public internet without protection
- Give docker socket access without restrictions
- Ignore security updates
- Run as root user
- Store passwords in plaintext
- Skip input validation
- Disable security features
- Forget to backup

---

## Compliance & Standards

### OWASP Top 10 Coverage

| Risk | Status | Mitigation |
|------|--------|-----------|
| Injection | ⚠️ Partial | SQLAlchemy ORM protects against SQL injection |
| Broken Authentication | ❌ Vulnerable | Needs MFA, account lockout |
| Sensitive Data Exposure | ❌ Vulnerable | No encryption at rest, needs HTTPS |
| XML External Entities | ✅ N/A | No XML processing |
| Broken Access Control | ⚠️ Partial | @login_required but no RBAC |
| Security Misconfiguration | ❌ Vulnerable | Needs security headers |
| XSS | ⚠️ Partial | Jinja2 auto-escaping but needs CSP |
| Insecure Deserialization | ✅ Protected | No deserialization of untrusted data |
| Using Components with Known Vulnerabilities | ⚠️ Unknown | Needs dependency scanning |
| Insufficient Logging | ❌ Vulnerable | Needs audit logging |

---

## Getting Help

### Report Security Issues

**DO NOT** create public GitHub issues for security vulnerabilities.

Instead, email: security@dockdash.example (private)

Include:
- Description of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Security Resources

- [OWASP Cheat Sheets](https://cheatsheetseries.owasp.org/)
- [Flask Security Guide](https://flask.palletsprojects.com/en/3.0.x/security/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)

---

**Last Updated:** February 1, 2026  
**Next Review:** March 1, 2026
