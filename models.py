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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
