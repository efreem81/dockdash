"""
DockDash Configuration
Centralized configuration and Flask app factory
"""
import os
import secrets
from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# Extensions (initialized without app)
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))


def create_app():
    """Application factory for Flask app."""
    app = Flask(__name__)
    
    # Secret key
    _secret_key = os.environ.get('SECRET_KEY')
    if not _secret_key:
        _secret_key = secrets.token_hex(32)
        print("WARNING: SECRET_KEY not set; using a temporary random key.")
    app.config['SECRET_KEY'] = _secret_key
    
    # Session/cookie hardening
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SAMESITE'] = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
    app.config['REMEMBER_COOKIE_SECURE'] = os.environ.get('REMEMBER_COOKIE_SECURE', '0') == '1'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        hours=int(os.environ.get('SESSION_LIFETIME_HOURS', '12'))
    )
    
    # Database
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "data", "dockdash.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    csrf.init_app(app)
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.containers import containers_bp
    from routes.images import images_bp
    from routes.urls import urls_bp
    from routes.notifications import notifications_bp
    from routes.vulnerabilities import vulnerabilities_bp
    from routes.monitoring import monitoring_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(containers_bp, url_prefix='/api')
    app.register_blueprint(images_bp, url_prefix='/api')
    app.register_blueprint(urls_bp)
    app.register_blueprint(notifications_bp, url_prefix='/api')
    app.register_blueprint(vulnerabilities_bp, url_prefix='/api')
    app.register_blueprint(monitoring_bp, url_prefix='/api')
    
    # Error handlers
    from flask_wtf.csrf import CSRFError
    from flask import jsonify, request, redirect, url_for, flash
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'CSRF token missing or invalid'}), 400
        flash('Session expired or request blocked (CSRF). Please try again.', 'error')
        return redirect(request.referrer or url_for('dashboard.dashboard'))
    
    # Initialize database
    with app.app_context():
        _init_db(app)
    
    # Auto-start monitoring if enabled
    if os.environ.get('AUTO_START_MONITORING', '0') == '1':
        try:
            from services.scheduler_service import start_monitoring
            start_monitoring()
            print("Background monitoring started automatically")
        except Exception as e:
            print(f"Failed to start monitoring: {e}")
    
    return app


def _init_db(app):
    """Initialize database and create default user."""
    from models import User
    
    db_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(db_dir, exist_ok=True)
    
    try:
        db.create_all()
        if User.query.count() == 0:
            default_username = os.environ.get('DEFAULT_USERNAME', 'admin')
            default_password = os.environ.get('DEFAULT_PASSWORD', 'dockdash')
            user = User(username=default_username)
            user.set_password(default_password)
            db.session.add(user)
            db.session.commit()
            print(f"Created default user: {default_username}")
    except Exception as e:
        print(f"Database initialization error: {e}")
