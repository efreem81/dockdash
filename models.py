"""
DockDash Database Models
"""
from datetime import datetime
import json
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from config import db, login_manager


class User(UserMixin, db.Model):
    """User account model."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SharedURL(db.Model):
    """Shared URL bookmark model."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), default='General')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('urls', lazy=True))


class WebhookConfig(db.Model):
    """Webhook notification configuration."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    webhook_type = db.Column(db.String(50), nullable=False)  # discord, slack, telegram, generic
    webhook_url = db.Column(db.String(500), nullable=False)
    enabled = db.Column(db.Boolean, default=True)

    # Alert settings
    alert_container_stop = db.Column(db.Boolean, default=True)
    alert_container_start = db.Column(db.Boolean, default=False)
    alert_health_unhealthy = db.Column(db.Boolean, default=True)
    alert_cpu_threshold = db.Column(db.Integer, default=90)  # percentage
    alert_memory_threshold = db.Column(db.Integer, default=90)  # percentage

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContainerState(db.Model):
    """Track container state for detecting changes."""
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(64), unique=True, nullable=False)
    container_name = db.Column(db.String(200), nullable=False)
    last_status = db.Column(db.String(50), nullable=False)
    last_health = db.Column(db.String(50), nullable=True)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)


class ImageUpdate(db.Model):
    """Store image update check results."""
    id = db.Column(db.Integer, primary_key=True)
    image_ref = db.Column(db.String(500), unique=True, nullable=False)
    has_update = db.Column(db.Boolean, default=False)
    local_digest = db.Column(db.String(100), nullable=True)
    remote_digest = db.Column(db.String(100), nullable=True)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow)
    error = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'image': self.image_ref,
            'has_update': self.has_update,
            'local_digest': self.local_digest,
            'remote_digest': self.remote_digest,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
            'error': self.error
        }


class ImageVulnerability(db.Model):
    """Store vulnerability scan results for container images."""
    id = db.Column(db.Integer, primary_key=True)
    image_ref = db.Column(db.String(500), unique=True, nullable=False)
    critical_count = db.Column(db.Integer, default=0)
    high_count = db.Column(db.Integer, default=0)
    medium_count = db.Column(db.Integer, default=0)
    low_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)
    vulnerabilities_json = db.Column(db.Text, nullable=True)  # Full vulnerability details as JSON
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    scan_duration_seconds = db.Column(db.Float, nullable=True)
    error = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'image': self.image_ref,
            'critical': self.critical_count,
            'high': self.high_count,
            'medium': self.medium_count,
            'low': self.low_count,
            'total': self.total_count,
            'scanned_at': self.scanned_at.isoformat() if self.scanned_at else None,
            'error': self.error
        }

    def get_vulnerabilities(self):
        """Get full vulnerability list from stored JSON."""
        if not self.vulnerabilities_json:
            return []
        try:
            import json
            return json.loads(self.vulnerabilities_json)
        except Exception:
            return []


class ScanSettings(db.Model):
    """Vulnerability scanning configuration (singleton)."""
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    schedule_type = db.Column(db.String(20), default='daily')  # 'manual', 'daily', 'weekly'
    schedule_hour = db.Column(db.Integer, default=3)  # Hour of day (0-23)
    schedule_minute = db.Column(db.Integer, default=0)
    schedule_day = db.Column(db.Integer, default=0)  # 0=Monday for weekly
    severity_filter = db.Column(db.String(50), default='CRITICAL,HIGH,MEDIUM,LOW')
    log_level = db.Column(db.String(10), default='INFO')  # DEBUG, INFO, WARNING, ERROR
    last_scan_started = db.Column(db.DateTime, nullable=True)
    last_scan_completed = db.Column(db.DateTime, nullable=True)
    last_scan_images_count = db.Column(db.Integer, default=0)

    @staticmethod
    def get_settings():
        """Get or create the singleton settings."""
        settings = ScanSettings.query.first()
        if not settings:
            settings = ScanSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class UpdateSettings(db.Model):
    """Update check configuration (singleton)."""
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    schedule_type = db.Column(db.String(20), default='daily')  # 'manual', 'daily', 'weekly'
    schedule_hour = db.Column(db.Integer, default=4)  # Hour of day (0-23)
    schedule_minute = db.Column(db.Integer, default=0)
    schedule_day = db.Column(db.Integer, default=0)  # 0=Monday for weekly
    last_check_started = db.Column(db.DateTime, nullable=True)
    last_check_completed = db.Column(db.DateTime, nullable=True)
    last_check_images_count = db.Column(db.Integer, default=0)
    images_with_updates = db.Column(db.Integer, default=0)

    @staticmethod
    def get_settings():
        """Get or create the singleton settings."""
        settings = UpdateSettings.query.first()
        if not settings:
            settings = UpdateSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class AppSettings(db.Model):
    """Application-level settings (singleton)."""
    id = db.Column(db.Integer, primary_key=True)
    log_level = db.Column(db.String(10), default='INFO')  # DEBUG, INFO, WARNING, ERROR

    @staticmethod
    def get_settings():
        """Get or create the singleton settings."""
        settings = AppSettings.query.first()
        if not settings:
            settings = AppSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class Endpoint(db.Model):
    """A Docker host managed directly or through a DockDash agent."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='local')  # local, agent
    url = db.Column(db.String(500), nullable=True)
    public_ip = db.Column(db.String(255), nullable=True)
    state_hint = db.Column(db.String(20), nullable=False, default='online')
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    tls_server_name = db.Column(db.String(255), nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    last_checked = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        if self.enabled is False:
            status = 'disabled'
        elif self.last_checked is None:
            status = 'unknown'
        elif self.last_error:
            status = 'offline'
        else:
            status = 'online'
        return {
            'id': self.id,
            'name': self.name,
            'kind': self.kind,
            'url': self.url,
            'public_ip': self.public_ip,
            'state_hint': self.state_hint,
            'enabled': self.enabled,
            'status': status,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'last_error': self.last_error,
        }


class ComposeProject(db.Model):
    """An adopted, Git-backed, or DockDash-managed Compose project."""
    __table_args__ = (db.UniqueConstraint('endpoint_id', 'name', name='uq_project_endpoint_name'),)

    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('endpoint.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    working_dir = db.Column(db.String(1000), nullable=False)
    config_files_json = db.Column(db.Text, nullable=False, default='[]')
    source_type = db.Column(db.String(20), nullable=False, default='adopted')
    repo_url = db.Column(db.String(1000), nullable=True)
    repo_ref = db.Column(db.String(255), nullable=True)
    compose_path = db.Column(db.String(500), nullable=True)
    required_mounts_json = db.Column(db.Text, nullable=False, default='[]')
    healthcheck_url = db.Column(db.String(1000), nullable=True)
    healthcheck_timeout = db.Column(db.Integer, nullable=False, default=120)
    healthcheck_statuses_json = db.Column(db.Text, nullable=False, default='[]')
    config_digest = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    endpoint = db.relationship('Endpoint', backref=db.backref('projects', lazy=True))

    @property
    def config_files(self):
        try:
            return json.loads(self.config_files_json or '[]')
        except Exception:
            return []

    @config_files.setter
    def config_files(self, value):
        self.config_files_json = json.dumps(value or [])

    @property
    def required_mounts(self):
        try:
            return json.loads(self.required_mounts_json or '[]')
        except Exception:
            return []

    @required_mounts.setter
    def required_mounts(self, value):
        self.required_mounts_json = json.dumps(value or [])

    @property
    def healthcheck_statuses(self):
        try:
            return [int(value) for value in json.loads(self.healthcheck_statuses_json or '[]')]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    @healthcheck_statuses.setter
    def healthcheck_statuses(self, value):
        self.healthcheck_statuses_json = json.dumps([int(item) for item in (value or [])])

    def to_dict(self):
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'endpoint_name': self.endpoint.name if self.endpoint else None,
            'name': self.name,
            'working_dir': self.working_dir,
            'config_files': self.config_files,
            'source_type': self.source_type,
            'repo_url': self.repo_url,
            'repo_ref': self.repo_ref,
            'compose_path': self.compose_path,
            'required_mounts': self.required_mounts,
            'healthcheck_url': self.healthcheck_url,
            'healthcheck_timeout': self.healthcheck_timeout,
            'healthcheck_statuses': self.healthcheck_statuses,
            'config_digest': self.config_digest,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class DeploymentRevision(db.Model):
    """Sanitized deployment revision and rollback evidence."""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('compose_project.id'), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    source_revision = db.Column(db.String(255), nullable=True)
    config_digest = db.Column(db.String(64), nullable=True)
    compose_content = db.Column(db.Text, nullable=True)
    image_state_json = db.Column(db.Text, nullable=False, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('ComposeProject', backref=db.backref('revisions', lazy=True, order_by='DeploymentRevision.revision'))

    @property
    def image_state(self):
        try:
            return json.loads(self.image_state_json or '{}')
        except Exception:
            return {}

    @image_state.setter
    def image_state(self, value):
        self.image_state_json = json.dumps(value or {})

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'revision': self.revision,
            'source_revision': self.source_revision,
            'config_digest': self.config_digest,
            'image_state': self.image_state,
            'editable': self.compose_content is not None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class OperationJob(db.Model):
    """Durable journal for remote and local lifecycle operations."""
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('endpoint.id'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('compose_project.id'), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='queued')
    stage = db.Column(db.String(80), nullable=True)
    request_json = db.Column(db.Text, nullable=False, default='{}')
    before_state_json = db.Column(db.Text, nullable=False, default='{}')
    after_state_json = db.Column(db.Text, nullable=False, default='{}')
    output = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    requested_by = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    endpoint = db.relationship('Endpoint')
    project = db.relationship('ComposeProject', backref=db.backref('operations', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'endpoint_name': self.endpoint.name if self.endpoint else None,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'action': self.action,
            'status': self.status,
            'stage': self.stage,
            'output': self.output,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
