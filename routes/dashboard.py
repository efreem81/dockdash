"""
Dashboard Routes
Main dashboard and health endpoints
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import text

from services.docker_service import get_all_containers, get_host_ip, get_docker_client
from config import db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    containers = get_all_containers(show_all=show_all)
    host_ip = get_host_ip()
    docker_available = get_docker_client() is not None
    
    # Group containers by compose project
    compose_groups = {}
    standalone = []
    for c in containers:
        project = c.get('compose_project')
        if project:
            if project not in compose_groups:
                compose_groups[project] = []
            compose_groups[project].append(c)
        else:
            standalone.append(c)
    
    return render_template('dashboard.html', 
                         containers=containers,
                         compose_groups=compose_groups,
                         standalone_containers=standalone,
                         host_ip=host_ip, 
                         show_all=show_all,
                         docker_available=docker_available)


@dashboard_bp.route('/health')
def health():
    """Lightweight health endpoint for container health checks."""
    docker_client = get_docker_client()
    docker_ok = docker_client is not None
    db_ok = False
    try:
        db.session.execute(text('SELECT 1'))
        db_ok = True
    except Exception:
        pass

    # Return 503 if database is down (critical), 200 otherwise
    status = 'ok' if db_ok else 'degraded'
    http_status = 200 if db_ok else 503
    
    return jsonify({
        'status': status,
        'docker_available': docker_ok,
        'database_ok': db_ok,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), http_status
