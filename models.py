"""
DockDash Database Models
"""
from datetime import datetime
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


class ImageVulnerability(db.Model):
    """Store vulnerability scan results for container images."""
    id = db.Column(db.Integer, primary_key=True)
    image_ref = db.Column(db.String(500), unique=True, nullable=False)
    critical_count = db.Column(db.Integer, default=0)
    high_count = db.Column(db.Integer, default=0)
    medium_count = db.Column(db.Integer, default=0)
    low_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)
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


class ScanSettings(db.Model):
    """Vulnerability scanning configuration (singleton)."""
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    schedule_type = db.Column(db.String(20), default='daily')  # 'manual', 'daily', 'weekly'
    schedule_hour = db.Column(db.Integer, default=3)  # Hour of day (0-23)
    schedule_minute = db.Column(db.Integer, default=0)
    schedule_day = db.Column(db.Integer, default=0)  # 0=Monday for weekly
    severity_filter = db.Column(db.String(50), default='CRITICAL,HIGH,MEDIUM,LOW')
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
