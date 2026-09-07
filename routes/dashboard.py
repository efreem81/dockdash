"""
Dashboard Routes
Main dashboard and health endpoints
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from services.docker_service import get_host_ip, get_docker_client
from services.fleet_service import annotate_container_management, get_endpoint, list_containers
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
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    endpoints = Endpoint.query.filter_by(enabled=True).order_by(Endpoint.name).all()
    all_hosts = request.args.get('endpoint_id') == 'all'
    endpoint = None if all_hosts else get_endpoint(remember=True)
    endpoint_errors = []
    available_endpoint_count = 0
    containers = []

    # Get vulnerability scan results
    from services.vulnerability_service import get_stored_vulnerabilities
    from services.update_service import get_stored_updates

    vuln_results = {}
    update_results = {}
    selected_endpoints = endpoints if all_hosts else [endpoint]
    for selected_endpoint in selected_endpoints:
        try:
            endpoint_containers = list_containers(
                selected_endpoint,
                show_all=show_all,
                timeout=5 if all_hosts else None,
            )
            # Keep mocked/legacy inventory and current agents on the same UI
            # capability contract.
            if endpoint_containers and 'management' not in endpoint_containers[0]:
                endpoint_containers = annotate_container_management(
                    selected_endpoint, endpoint_containers,
                )
            available_endpoint_count += 1
        except Exception as exc:
            endpoint_containers = []
            endpoint_errors.append({
                'id': selected_endpoint.id,
                'name': selected_endpoint.name,
                'error': str(exc),
            })

        endpoint_vulnerabilities = get_stored_vulnerabilities(endpoint_id=selected_endpoint.id)
        endpoint_updates = get_stored_updates(endpoint_id=selected_endpoint.id)
        for image_ref, result in endpoint_vulnerabilities.items():
            vuln_results[f'{selected_endpoint.id}:{image_ref}'] = result
        for image_ref, result in endpoint_updates.items():
            update_results[f'{selected_endpoint.id}:{image_ref}'] = result

        endpoint_host = selected_endpoint.public_ip or (
            get_host_ip() if selected_endpoint.kind == 'local' else None
        )
        for container in endpoint_containers:
            container['endpoint_id'] = selected_endpoint.id
            container['endpoint_name'] = selected_endpoint.name
            container['endpoint_host'] = endpoint_host
            image_ref = container.get('image', '')
            if image_ref in endpoint_vulnerabilities:
                container['vulnerabilities'] = endpoint_vulnerabilities[image_ref]
            if image_ref in endpoint_updates:
                container['has_update'] = endpoint_updates[image_ref].get('has_update', False)
            containers.append(container)

    docker_available = available_endpoint_count > 0
    host_ip = None if all_hosts else (endpoint.public_ip or get_host_ip())

    # Group containers by compose project
    compose_groups = {}
    standalone = []
    updates_count = 0
    for c in containers:
        if c.get('has_update'):
            updates_count += 1

        project = c.get('compose_project')
        if project:
            group_name = f"{c['endpoint_name']} / {project}" if all_hosts else project
            if group_name not in compose_groups:
                compose_groups[group_name] = []
            compose_groups[group_name].append(c)
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
                         endpoints=endpoints,
                         all_hosts=all_hosts,
                         endpoint_errors=endpoint_errors,
                         available_endpoint_count=available_endpoint_count)


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
