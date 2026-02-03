"""
Container API Routes
Container management endpoints: start, stop, restart, logs, stats, exec, remove
"""
import time
import requests
from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.docker_service import (
    get_docker_client, get_all_containers, get_container_info,
    get_container_stats, exec_container, remove_container,
    prune_containers, get_host_ip
)
from services.lifecycle_service import recreate_container

containers_bp = Blueprint('containers', __name__)

# Cache for HTTP probing
_probe_cache = {}


def _cache_get(key, ttl_seconds):
    entry = _probe_cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if (time.time() - ts) > ttl_seconds:
        _probe_cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _probe_cache[key] = (time.time(), value)


@containers_bp.route('/containers')
@login_required
def api_containers():
    show_all = request.args.get('show_all', 'false').lower() == 'true'
    containers = get_all_containers(show_all=show_all)
    return jsonify(containers)


@containers_bp.route('/container/<container_id>')
@login_required
def api_container_detail(container_id):
    """Get detailed info for a single container."""
    client = get_docker_client()
    if not client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    try:
        container = client.containers.get(container_id)
        return jsonify({'success': True, 'container': get_container_info(container)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 404


@containers_bp.route('/container/<container_id>/stats')
@login_required
def api_container_stats(container_id):
    """Get real-time stats for a container."""
    stats = get_container_stats(container_id)
    if stats and 'error' not in stats:
        return jsonify({'success': True, 'stats': stats})
    return jsonify({'success': False, 'error': stats.get('error', 'Unknown error')}), 500


@containers_bp.route('/container/<container_id>/restart', methods=['POST'])
@login_required
def restart_container(container_id):
    client = get_docker_client()
    if not client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    try:
        container = client.containers.get(container_id)
        container.restart()
        return jsonify({'success': True, 'message': f'Container {container.name} restarted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@containers_bp.route('/container/<container_id>/stop', methods=['POST'])
@login_required
def stop_container(container_id):
    client = get_docker_client()
    if not client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    try:
        container = client.containers.get(container_id)
        container.stop()
        return jsonify({'success': True, 'message': f'Container {container.name} stopped'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@containers_bp.route('/container/<container_id>/start', methods=['POST'])
@login_required
def start_container(container_id):
    client = get_docker_client()
    if not client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500
    try:
        container = client.containers.get(container_id)
        container.start()
        return jsonify({'success': True, 'message': f'Container {container.name} started'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@containers_bp.route('/container/<container_id>/remove', methods=['POST'])
@login_required
def api_remove_container(container_id):
    """Remove a container."""
    force = request.json.get('force', False) if request.is_json else False
    result = remove_container(container_id, force=force)
    status = 200 if result['success'] else 500
    return jsonify(result), status


@containers_bp.route('/container/<container_id>/logs')
@login_required
def container_logs(container_id):
    client = get_docker_client()
    if not client:
        return jsonify({'success': False, 'error': 'Docker not available'}), 500

    tail = request.args.get('tail', '200')
    timestamps = request.args.get('timestamps', '1') == '1'
    try:
        tail_n = max(1, min(2000, int(tail)))
    except Exception:
        tail_n = 200

    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=tail_n, timestamps=timestamps)
        logs_text = logs.decode('utf-8', errors='replace') if isinstance(logs, bytes) else str(logs)
        return jsonify({'success': True, 'container': container.name, 'logs': logs_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@containers_bp.route('/container/<container_id>/exec', methods=['POST'])
@login_required
def api_exec_container(container_id):
    """Execute a command in a container."""
    data = request.get_json() or {}
    command = data.get('command')
    workdir = data.get('workdir')
    
    if not command:
        return jsonify({'success': False, 'error': 'Command required'}), 400
    
    result = exec_container(container_id, command, workdir)
    status = 200 if result['success'] else 500
    return jsonify(result), status


@containers_bp.route('/containers/prune', methods=['POST'])
@login_required
def api_prune_containers():
    """Remove all stopped containers."""
    result = prune_containers()
    status = 200 if result['success'] else 500
    return jsonify(result), status


@containers_bp.route('/container/<container_id>/recreate', methods=['POST'])
@login_required
def api_recreate_container(container_id):
    """Recreate a container with optionally updated image."""
    data = request.get_json() or {}
    pull_latest = data.get('pull_latest', True)
    
    result = recreate_container(container_id, pull_latest=pull_latest)
    
    # Clear update status for this image since we just updated
    if result.get('success') and result.get('image'):
        from services.update_service import clear_update_status
        clear_update_status(result['image'])
    
    status = 200 if result['success'] else 500
    return jsonify(result), status


@containers_bp.route('/containers/update-all', methods=['POST'])
@login_required
def api_update_all_containers():
    """Update all containers that have available updates."""
    from services.update_service import get_stored_updates, clear_update_status
    from services.docker_service import get_all_containers
    
    data = request.get_json() or {}
    container_ids = data.get('container_ids', [])  # Optional: specific containers to update
    
    # Get containers and their update status
    containers = get_all_containers(show_all=True)
    stored_updates = get_stored_updates()
    
    results = []
    success_count = 0
    error_count = 0
    
    for container in containers:
        container_id = container.get('id')
        container_name = container.get('name')
        image = container.get('image')
        
        # If specific containers requested, filter
        if container_ids and container_id not in container_ids and container_name not in container_ids:
            continue
        
        # Check if this container has an update
        update_info = stored_updates.get(image, {})
        if not update_info.get('has_update'):
            continue
        
        # Try to recreate
        try:
            result = recreate_container(container_id, pull_latest=True)
            if result.get('success'):
                success_count += 1
                clear_update_status(image)
                results.append({
                    'container': container_name,
                    'image': image,
                    'success': True,
                    'message': result.get('message')
                })
            else:
                error_count += 1
                results.append({
                    'container': container_name,
                    'image': image,
                    'success': False,
                    'error': result.get('error')
                })
        except Exception as e:
            error_count += 1
            results.append({
                'container': container_name,
                'image': image,
                'success': False,
                'error': str(e)
            })
    
    return jsonify({
        'success': error_count == 0,
        'updated': success_count,
        'errors': error_count,
        'results': results
    })


@containers_bp.route('/link/probe')
@login_required
def api_probe_link():
    """Probe a host:port and return whether https or http responds."""
    host = (request.args.get('host') or '').strip()
    port_raw = (request.args.get('port') or '').strip()

    try:
        port = int(port_raw)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid port'}), 400

    if port < 1 or port > 65535:
        return jsonify({'success': False, 'error': 'Invalid port'}), 400

    allowed_hosts = {get_host_ip(), 'localhost', '127.0.0.1'}
    if host not in allowed_hosts:
        return jsonify({'success': False, 'error': 'Host not allowed'}), 400

    cache_key = f"{host}:{port}"
    cached = _cache_get(cache_key, ttl_seconds=60)
    if cached:
        scheme, web = cached
    else:
        scheme, web = _probe_http_scheme(host, port)
        _cache_set(cache_key, (scheme, web))

    url = f"{scheme}://{host}:{port}" if web and scheme in ('http', 'https') else None

    return jsonify({
        'success': True,
        'scheme': scheme,
        'web': web,
        'url': url,
        'host': host,
        'port': port
    })


def _probe_http_scheme(host, port):
    """Return (scheme, web) where scheme is 'https'|'http'|'unknown'."""
    headers = {'User-Agent': 'DockDashProbe/1.0', 'Accept': '*/*'}
    
    # Try HTTPS first
    try:
        r = requests.head(f"https://{host}:{port}", timeout=1.5, allow_redirects=True, 
                         verify=False, headers=headers)
        r.close()
        return 'https', True
    except Exception:
        pass
    
    # Try HTTP
    try:
        r = requests.head(f"http://{host}:{port}", timeout=1.5, allow_redirects=True, 
                         headers=headers)
        r.close()
        return 'http', True
    except Exception:
        pass
    
    return 'unknown', False
