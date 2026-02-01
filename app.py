import os
import docker
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

# Use absolute path for database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "data", "dockdash.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Initialize Docker/Podman client
# Supports both Docker and Podman (Docker-compatible API)
try:
    # Try custom socket path from environment (for Podman)
    socket_path = os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock')
    if socket_path.startswith('unix://'):
        docker_client = docker.DockerClient(base_url=socket_path)
    else:
        docker_client = docker.from_env()
except docker.errors.DockerException:
    docker_client = None


# =============================================================================
# Database Models
# =============================================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SharedURL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), default='General')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('urls', lazy=True))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =============================================================================
# Helper Functions
# =============================================================================

def get_host_ip():
    """Get the host IP address for container URL generation."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_container_info(container):
    """Extract relevant information from a Docker container."""
    info = {
        'id': container.short_id,
        'name': container.name,
        'status': container.status,
        'image': container.image.tags[0] if container.image.tags else 'unknown',
        'created': container.attrs['Created'][:19].replace('T', ' '),
        'ports': [],
        'urls': []
    }
    
    # Get port mappings
    ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
    host_ip = get_host_ip()
    
    for container_port, bindings in ports.items():
        if bindings:
            for binding in bindings:
                host_port = binding.get('HostPort')
                if host_port:
                    port_info = {
                        'container_port': container_port,
                        'host_port': host_port,
                        'url': f"http://{host_ip}:{host_port}"
                    }
                    info['ports'].append(port_info)
                    info['urls'].append(port_info['url'])
    
    return info


def get_all_containers(show_all=False):
    """Get all Docker containers."""
    if not docker_client:
        return []
    
    try:
        containers = docker_client.containers.list(all=show_all)
        return [get_container_info(c) for c in containers]
    except Exception as e:
        print(f"Error getting containers: {e}")
        return []


def init_default_user():
    """Create default admin user if no users exist."""
    if User.query.count() == 0:
        default_username = os.environ.get('DEFAULT_USERNAME', 'admin')
        default_password = os.environ.get('DEFAULT_PASSWORD', 'dockdash')
        
        user = User(username=default_username)
        user.set_password(default_password)
        db.session.add(user)
        db.session.commit()
        print(f"Created default user: {default_username}")


# =============================================================================
# Routes - Authentication
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'error')
        elif len(new_password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')


# =============================================================================
# Routes - Dashboard & Containers
# =============================================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    containers = get_all_containers(show_all=show_all)
    host_ip = get_host_ip()
    docker_available = docker_client is not None
    return render_template('dashboard.html', 
                         containers=containers, 
                         host_ip=host_ip, 
                         show_all=show_all,
                         docker_available=docker_available)


@app.route('/api/containers')
@login_required
def api_containers():
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    containers = get_all_containers(show_all=show_all)
    return jsonify(containers)


@app.route('/api/container/<container_id>/restart', methods=['POST'])
@login_required
def restart_container(container_id):
    if not docker_client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    
    try:
        container = docker_client.containers.get(container_id)
        container.restart()
        return jsonify({'success': True, 'message': f'Container {container.name} restarted'})
    except docker.errors.NotFound:
        return jsonify({'success': False, 'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/container/<container_id>/stop', methods=['POST'])
@login_required
def stop_container(container_id):
    if not docker_client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    
    try:
        container = docker_client.containers.get(container_id)
        container.stop()
        return jsonify({'success': True, 'message': f'Container {container.name} stopped'})
    except docker.errors.NotFound:
        return jsonify({'success': False, 'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/container/<container_id>/start', methods=['POST'])
@login_required
def start_container(container_id):
    if not docker_client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    
    try:
        container = docker_client.containers.get(container_id)
        container.start()
        return jsonify({'success': True, 'message': f'Container {container.name} started'})
    except docker.errors.NotFound:
        return jsonify({'success': False, 'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Routes - URL Sharing
# =============================================================================

@app.route('/urls')
@login_required
def url_list():
    category = request.args.get('category', None)
    if category:
        urls = SharedURL.query.filter_by(category=category).order_by(SharedURL.created_at.desc()).all()
    else:
        urls = SharedURL.query.order_by(SharedURL.created_at.desc()).all()
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('urls.html', urls=urls, categories=categories, current_category=category)


@app.route('/urls/add', methods=['GET', 'POST'])
@login_required
def add_url():
    if request.method == 'POST':
        title = request.form.get('title')
        url = request.form.get('url')
        description = request.form.get('description')
        category = request.form.get('category') or 'General'
        
        if not title or not url:
            flash('Title and URL are required', 'error')
        else:
            shared_url = SharedURL(
                title=title,
                url=url,
                description=description,
                category=category,
                created_by=current_user.id
            )
            db.session.add(shared_url)
            db.session.commit()
            flash('URL added successfully!', 'success')
            return redirect(url_for('url_list'))
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('add_url.html', categories=categories)


@app.route('/urls/<int:url_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_url(url_id):
    shared_url = SharedURL.query.get_or_404(url_id)
    
    if request.method == 'POST':
        shared_url.title = request.form.get('title')
        shared_url.url = request.form.get('url')
        shared_url.description = request.form.get('description')
        shared_url.category = request.form.get('category') or 'General'
        
        if not shared_url.title or not shared_url.url:
            flash('Title and URL are required', 'error')
        else:
            db.session.commit()
            flash('URL updated successfully!', 'success')
            return redirect(url_for('url_list'))
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('edit_url.html', shared_url=shared_url, categories=categories)


@app.route('/urls/<int:url_id>/delete', methods=['POST'])
@login_required
def delete_url(url_id):
    shared_url = SharedURL.query.get_or_404(url_id)
    db.session.delete(shared_url)
    db.session.commit()
    flash('URL deleted successfully!', 'success')
    return redirect(url_for('url_list'))


@app.route('/api/urls')
@login_required
def api_urls():
    urls = SharedURL.query.order_by(SharedURL.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'title': u.title,
        'url': u.url,
        'description': u.description,
        'category': u.category,
        'created_at': u.created_at.isoformat()
    } for u in urls])


# =============================================================================
# Application Initialization
# =============================================================================

def init_db():
    """Initialize the database safely."""
    # Ensure data directory exists before creating database
    db_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(db_dir, exist_ok=True)
    
    try:
        db.create_all()
        init_default_user()
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Don't fail startup - database might be initializing in another worker


# Track if database has been initialized
_db_initialized = False

@app.before_request
def before_request():
    """Initialize database on first request."""
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            print(f"Database initialization deferred: {e}")


# Also try initialization at startup
with app.app_context():
    try:
        init_db()
        _db_initialized = True
    except Exception:
        # Will retry on first request
        pass


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
