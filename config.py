"""
DockDash Configuration
Centralized configuration and Flask app factory
"""
import os
import secrets
import time
from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

# Extensions (initialized without app)
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))
default_database_path = os.path.join(basedir, 'data', 'dockdash.db')
default_database_uri = f'sqlite:///{default_database_path}'


def create_app(test_config=None):
    """Application factory for Flask app."""
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)

    # Basic logging (may be refined after DB init)
    try:
        from services.logging_service import configure_app_logging
        configure_app_logging(app)
    except Exception as exc:
        app.logger.warning('Initial logging configuration failed: %s', exc)

    # Secret key
    _secret_key = app.config.get('SECRET_KEY') or os.environ.get('SECRET_KEY')
    if not _secret_key:
        if app.config.get('TESTING'):
            _secret_key = secrets.token_hex(32)
        else:
            raise RuntimeError('SECRET_KEY must be set outside testing')
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
    app.config['SQLALCHEMY_DATABASE_URI'] = default_database_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Explicit test/embedding configuration has final precedence over defaults.
    if test_config:
        app.config.update(test_config)
    if app.config['SQLALCHEMY_DATABASE_URI'] == default_database_uri:
        # Keep the restrictive umask for the process lifetime so SQLite can
        # never create a world-readable database, WAL, or SHM file later.
        os.umask(0o077)
        os.makedirs(os.path.dirname(default_database_path), mode=0o700, exist_ok=True)
        os.chmod(os.path.dirname(default_database_path), 0o700)
        for database_file in (
            default_database_path,
            f'{default_database_path}-wal',
            f'{default_database_path}-shm',
        ):
            if os.path.exists(database_file):
                os.chmod(database_file, 0o600)
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
    from routes.logging import logging_bp
    from routes.fleet import fleet_bp
    from routes.projects import projects_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(containers_bp, url_prefix='/api')
    app.register_blueprint(images_bp, url_prefix='/api')
    app.register_blueprint(urls_bp)
    app.register_blueprint(notifications_bp, url_prefix='/api')
    app.register_blueprint(vulnerabilities_bp, url_prefix='/api')
    app.register_blueprint(monitoring_bp, url_prefix='/api')
    app.register_blueprint(logging_bp, url_prefix='/api')
    app.register_blueprint(fleet_bp)
    app.register_blueprint(projects_bp)

    # Error handlers
    from flask_wtf.csrf import CSRFError
    from flask import jsonify, request, redirect, url_for, flash
    from services.fleet_service import EndpointSelectionError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'CSRF token missing or invalid'}), 400
        flash('Session expired or request blocked (CSRF). Please try again.', 'error')
        return redirect(request.referrer or url_for('dashboard.dashboard'))

    @app.errorhandler(EndpointSelectionError)
    def handle_endpoint_selection_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': str(error)}), 404
        return str(error), 404

    # Initialize database
    with app.app_context():
        initialize_database = app.config.get(
            'INITIALIZE_DATABASE',
            os.environ.get('DOCKDASH_SKIP_DB_INIT', '0') != '1',
        )
        if initialize_database:
            _init_db(app)
        else:
            errors = database_schema_errors()
            if errors:
                raise RuntimeError('Database schema is not ready: ' + '; '.join(errors))

        # Apply DB-configured log level once DB is ready
        try:
            from services.logging_service import configure_app_logging
            configure_app_logging(app)
        except Exception as exc:
            app.logger.warning('Database-backed logging configuration failed: %s', exc)

    # Request/response debug logging (API-focused, redacts sensitive inputs)
    import logging
    from flask import g

    req_logger = logging.getLogger('dockdash.http')

    @app.before_request
    def _log_request_start():
        if not (request.path.startswith('/api/') or request.endpoint):
            return
        g._dockdash_start_time = time.time()

        # Don't log sensitive form bodies.
        sensitive = any(x in (request.path or '') for x in ('login', 'password'))
        json_keys = None
        if request.is_json and not sensitive:
            try:
                payload = request.get_json(silent=True) or {}
                if isinstance(payload, dict):
                    json_keys = sorted(payload.keys())
                else:
                    json_keys = ['<non-dict-json>']
            except Exception:
                json_keys = ['<unreadable-json>']

        req_logger.debug(
            'REQ %s %s args=%s json_keys=%s',
            request.method,
            request.path,
            dict(request.args) if request.args else {},
            json_keys,
        )

    @app.after_request
    def _log_request_end(response):
        try:
            start = getattr(g, '_dockdash_start_time', None)
            if start is not None and (request.path.startswith('/api/') or request.endpoint):
                ms = int((time.time() - start) * 1000)
                req_logger.debug('RES %s %s status=%s ms=%s', request.method, request.path, response.status_code, ms)
        except Exception as exc:
            req_logger.debug('Could not record response timing: %s', exc)
        return response

    # Auto-start monitoring if enabled
    if os.environ.get('AUTO_START_MONITORING', '0') == '1':
        try:
            from services.scheduler_service import start_monitoring
            start_monitoring(app)
            print("Background monitoring started automatically")
        except Exception as e:
            print(f"Failed to start monitoring: {e}")

    return app


def _init_db(app):
    """Initialize database and create default user."""
    from models import User, Endpoint

    db.create_all()
    _run_migrations()
    errors = database_schema_errors()
    if errors:
        raise RuntimeError('Database schema validation failed: ' + '; '.join(errors))

    if User.query.count() == 0:
        default_username = os.environ.get('DEFAULT_USERNAME', 'admin')
        default_password = os.environ.get('DEFAULT_PASSWORD')
        if not default_password and app.config.get('TESTING'):
            default_password = secrets.token_urlsafe(24)
        if not default_password:
            raise RuntimeError('DEFAULT_PASSWORD must be set when creating the initial user')
        lowered_password = default_password.strip().lower()
        if not app.config.get('TESTING') and (
            lowered_password in {'dockdash', 'admin', 'password'}
            or lowered_password.startswith(('change-me', 'replace-me'))
        ):
            raise RuntimeError('DEFAULT_PASSWORD must not use a known default value')
        user = User(username=default_username)
        user.set_password(default_password)
        db.session.add(user)
        db.session.commit()
        print(f"Created default user: {default_username}")
    if Endpoint.query.count() == 0:
        endpoint = Endpoint(
            name=os.environ.get('LOCAL_ENDPOINT_NAME', 'DockerHost'),
            kind='local',
            public_ip=os.environ.get('HOST_IP') or None,
            state_hint='online',
        )
        db.session.add(endpoint)
        db.session.commit()


def _run_migrations():
    """Apply the small, ordered SQLite migrations required by current models."""
    migrations = (
        ('image_vulnerability', 'vulnerabilities_json', 'TEXT'),
        ('scan_settings', 'log_level', "VARCHAR(20) DEFAULT 'WARNING'"),
        ('compose_project', 'healthcheck_statuses_json', "TEXT NOT NULL DEFAULT '[]'"),
    )
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    for table_name, column_name, column_type in migrations:
        if table_name not in tables:
            continue
        columns = {column['name'] for column in inspector.get_columns(table_name)}
        if column_name not in columns:
            db.session.execute(text(
                f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'
            ))
            db.session.commit()
            inspector = inspect(db.engine)


def database_schema_errors():
    """Return missing tables/columns so startup and health fail closed."""
    try:
        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())
        errors = []
        for table in db.metadata.sorted_tables:
            if table.name not in actual_tables:
                errors.append(f'missing table {table.name}')
                continue
            actual_columns = {column['name'] for column in inspector.get_columns(table.name)}
            missing_columns = sorted(set(table.columns.keys()) - actual_columns)
            if missing_columns:
                errors.append(f'missing columns in {table.name}: {", ".join(missing_columns)}')
        return errors
    except Exception as exc:
        return [f'database inspection failed: {exc}']
