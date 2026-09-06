"""
Dashboard Routes
Main dashboard and health endpoints
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from services.docker_service import get_host_ip, get_docker_client
from services.fleet_service import get_endpoint, list_containers
from models import Endpoint
from config import database_schema_errors

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    endpoint = get_endpoint(remember=True)
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    try:
        containers = list_containers(endpoint, show_all=show_all)
        docker_available = True
    except Exception:
        containers = []
        docker_available = False
    host_ip = endpoint.public_ip or get_host_ip()
    endpoints = Endpoint.query.filter_by(enabled=True).order_by(Endpoint.name).all()

    # Get vulnerability scan results
    from services.vulnerability_service import get_stored_vulnerabilities
    vuln_results = get_stored_vulnerabilities()

    # Get update check results
    from services.update_service import get_stored_updates
    update_results = get_stored_updates()

    # Group containers by compose project
    compose_groups = {}
    standalone = []
    updates_count = 0
    for c in containers:
        # Attach vulnerability data to each container
        image = c.get('image', '')
        if image in vuln_results:
            c['vulnerabilities'] = vuln_results[image]

        # Attach update data to each container
        if image in update_results:
            has_update = update_results[image].get('has_update', False)
            c['has_update'] = has_update
            if has_update:
                updates_count += 1

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
                         docker_available=docker_available,
                         vuln_results=vuln_results,
                         update_results=update_results,
                         updates_count=updates_count,
                         endpoint=endpoint,
                         endpoints=endpoints)


@dashboard_bp.route('/health')
def health():
    """Lightweight health endpoint for container health checks."""
    docker_client = get_docker_client()
    docker_ok = docker_client is not None
    schema_errors = database_schema_errors()
    db_ok = not schema_errors

    # Return 503 if database is down (critical), 200 otherwise
    status = 'ok' if db_ok else 'degraded'
    http_status = 200 if db_ok else 503

    return jsonify({
        'status': status,
        'docker_available': docker_ok,
        'database_ok': db_ok,
        'database_schema_errors': schema_errors,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), http_status
