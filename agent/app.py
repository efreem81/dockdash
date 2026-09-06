"""DockDash Agent: a deliberately narrow, mTLS-protected Docker/Compose API."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
# Commands are fixed argv lists and never invoke a shell.
import subprocess  # nosec B404
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import docker
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
MAX_OUTPUT = int(os.environ.get('DOCKDASH_AGENT_MAX_OUTPUT', '50000'))
MIN_FREE_BYTES = int(os.environ.get('DOCKDASH_AGENT_MIN_FREE_BYTES', str(1024 ** 3)))
MANAGED_ROOT = os.path.realpath(os.environ.get('DOCKDASH_MANAGED_ROOT', '/opt/dockdash-managed'))
ROOTS = [os.path.realpath(p) for p in os.environ.get(
    'DOCKDASH_COMPOSE_ROOTS', '/home/eric/docker-compose,/opt'
).split(',') if p.strip()]
SCAN_ROOTS = [os.path.realpath(p) for p in os.environ.get(
    'DOCKDASH_SCAN_ROOTS', ','.join(ROOTS)
).split(',') if p.strip()]
COMPOSE_NAMES = {'compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml'}


def client():
    return docker.from_env(timeout=60)


def ok(**kwargs):
    return jsonify(success=True, **kwargs)


def fail(message, status=400):
    return jsonify(success=False, error=str(message)), status


def allowed_path(path, *, managed_only=False):
    resolved = os.path.realpath(path)
    roots = [MANAGED_ROOT] if managed_only else ROOTS + [MANAGED_ROOT]
    if not any(resolved == root or resolved.startswith(root + os.sep) for root in roots):
        raise ValueError(f'Path is outside configured Compose roots: {path}')
    return resolved


def bounded_int(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def format_bytes(size):
    value = float(size or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}'
        value /= 1024


def container_info(container):
    attrs = container.attrs
    config = attrs.get('Config') or {}
    state = attrs.get('State') or {}
    network_settings = attrs.get('NetworkSettings') or {}
    labels = config.get('Labels') or {}
    ports = []
    for container_port, bindings in (network_settings.get('Ports') or {}).items():
        port_num, _, protocol = container_port.partition('/')
        if not bindings:
            ports.append({'container_port': port_num, 'host_port': None, 'protocol': protocol or 'tcp'})
        else:
            for binding in bindings:
                ports.append({
                    'container_port': port_num,
                    'host_port': binding.get('HostPort'),
                    'host_ip': binding.get('HostIp'),
                    'protocol': protocol or 'tcp',
                })
    image_tags = container.image.tags if container.image else []
    image_name = config.get('Image') or (image_tags[0] if image_tags else 'unknown')
    env_vars = {}
    sensitive = ('password', 'passwd', 'secret', 'token', 'key', 'credential', 'private', 'auth')
    for item in config.get('Env') or []:
        key, _, value = item.partition('=')
        parsed_value = urlparse(value)
        embedded_auth = bool(parsed_value.scheme and (parsed_value.username or parsed_value.password))
        env_vars[key] = '********' if any(x in key.lower() for x in sensitive) or embedded_auth else value
    safe_labels = {}
    for key, value in labels.items():
        safe_labels[key] = '********' if any(x in key.lower() for x in sensitive) else value
    mounts = []
    for mount in attrs.get('Mounts') or []:
        mounts.append({
            'type': mount.get('Type'), 'source': mount.get('Source'),
            'destination': mount.get('Destination'), 'mode': mount.get('Mode'),
            'rw': mount.get('RW'), 'name': mount.get('Name'),
        })
    return {
        'id': container.id,
        'short_id': container.short_id,
        'name': container.name,
        'image': image_name,
        'image_id': container.image.id if container.image else None,
        'status': container.status,
        'health_status': (state.get('Health') or {}).get('Status'),
        'created': attrs.get('Created'),
        'ports': ports,
        'labels': safe_labels,
        'env_vars': env_vars,
        'mounts': mounts,
        'networks': list((network_settings.get('Networks') or {}).keys()),
        'compose_project': labels.get('com.docker.compose.project', ''),
        'compose_service': labels.get('com.docker.compose.service', ''),
        'state': state,
    }


def parse_stats(stats):
    cpu_delta = (stats.get('cpu_stats', {}).get('cpu_usage', {}).get('total_usage', 0) -
                 stats.get('precpu_stats', {}).get('cpu_usage', {}).get('total_usage', 0))
    system_delta = (stats.get('cpu_stats', {}).get('system_cpu_usage', 0) -
                    stats.get('precpu_stats', {}).get('system_cpu_usage', 0))
    cpus = stats.get('cpu_stats', {}).get('online_cpus') or len(
        stats.get('cpu_stats', {}).get('cpu_usage', {}).get('percpu_usage') or [1]
    )
    cpu = (cpu_delta / system_delta * cpus * 100.0) if system_delta > 0 and cpu_delta > 0 else 0
    mem = stats.get('memory_stats', {})
    usage = max(0, mem.get('usage', 0) - (mem.get('stats', {}).get('cache', 0) or 0))
    limit = mem.get('limit', 0)
    networks = stats.get('networks') or {}
    return {
        'cpu_percent': round(cpu, 2),
        'memory_usage': usage,
        'memory_limit': limit,
        'memory_percent': round(usage / limit * 100, 2) if limit else 0,
        'memory_usage_human': format_bytes(usage),
        'memory_limit_human': format_bytes(limit),
        'network_rx': sum(v.get('rx_bytes', 0) for v in networks.values()),
        'network_tx': sum(v.get('tx_bytes', 0) for v in networks.values()),
    }


def run(args, cwd=None, timeout=600):
    # Args are constructed from allowlisted actions and run with shell=False.
    completed = subprocess.run(  # nosec B603
        args, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout, check=False,
    )
    output = (completed.stdout or '')[-MAX_OUTPUT:]
    if completed.returncode:
        raise RuntimeError(f'Command failed ({completed.returncode}): {output}')
    return output


def compose_args(payload):
    working_dir = allowed_path(payload.get('working_dir') or '')
    args = ['docker', 'compose', '--project-directory', working_dir]
    for config_file in payload.get('config_files') or []:
        config_file = allowed_path(config_file)
        args.extend(['-f', config_file])
    if payload.get('name'):
        args.extend(['-p', payload['name']])
    return working_dir, args


def compose_state(payload):
    working_dir, args = compose_args(payload)
    output = run(args + ['ps', '--all', '--format', 'json'], cwd=working_dir, timeout=60)
    rows = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
            rows.extend(value if isinstance(value, list) else [value])
        except ValueError:
            continue
    images = {}
    for item in rows:
        service = item.get('Service') or item.get('Name')
        images[service] = {
            'image': item.get('Image'),
            'container': item.get('Name'),
            'state': item.get('State'),
            'health': item.get('Health'),
        }
        try:
            c = client().containers.get(item.get('ID') or item.get('Name'))
            images[service]['image_id'] = c.image.id
        except Exception as exc:
            app.logger.debug('Could not resolve image ID for Compose service %s: %s', service, exc)
    digest = project_digest(payload.get('config_files') or [])
    return {'containers': rows, 'images': images, 'config_digest': digest}


def project_digest(files):
    digest = hashlib.sha256()
    found = False
    for value in sorted(files):
        path = allowed_path(value)
        if os.path.isfile(path):
            found = True
            with open(path, 'rb') as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    digest.update(chunk)
    return digest.hexdigest() if found else None


def discover():
    projects = {}
    for container in client().containers.list(all=True):
        labels = container.labels or {}
        name = labels.get('com.docker.compose.project')
        working_dir = labels.get('com.docker.compose.project.working_dir')
        files = labels.get('com.docker.compose.project.config_files')
        if not name or not working_dir:
            continue
        try:
            working_dir = allowed_path(working_dir)
        except ValueError:
            continue
        config_files = [f.strip() for f in (files or '').split(',') if f.strip()]
        projects[name] = {
            'name': name, 'working_dir': working_dir, 'config_files': config_files,
            'discovery': 'labels',
        }
    max_depth = bounded_int(os.environ.get('DOCKDASH_SCAN_DEPTH'), 4, 1, 8)
    for root in SCAN_ROOTS + [MANAGED_ROOT]:
        if not os.path.isdir(root):
            continue
        root_depth = Path(root).parts
        for current, dirs, files in os.walk(root):
            depth = len(Path(current).parts) - len(root_depth)
            if depth >= max_depth:
                dirs[:] = []
            dirs[:] = [
                d for d in dirs
                if d not in {'.git', 'data', 'node_modules', '__pycache__', 'backup', 'backups', 'archive', 'archives'}
                and not re.search(r'(^|[-_.])(backup|bak|archive)([-_.]|$)', d, re.IGNORECASE)
            ]
            compose_files = [os.path.join(current, name) for name in files if name in COMPOSE_NAMES]
            if not compose_files:
                continue
            name = os.path.basename(current).lower().replace(' ', '-')
            if name not in projects:
                projects[name] = {
                    'name': name, 'working_dir': current,
                    'config_files': [sorted(compose_files)[0]], 'discovery': 'filesystem',
                }
    result = []
    for item in projects.values():
        files = item.get('config_files') or []
        if not files:
            files = [os.path.join(item['working_dir'], name) for name in COMPOSE_NAMES
                     if os.path.isfile(os.path.join(item['working_dir'], name))]
            item['config_files'] = files[:1]
        item['config_digest'] = project_digest(item['config_files'])
        try:
            working_dir, args = compose_args(item)
            services = run(args + ['config', '--services'], cwd=working_dir, timeout=45).splitlines()
            item['services'] = services
            item['valid'] = True
            state = compose_state(item)
            item['containers'] = state['containers']
        except Exception as exc:
            item['services'] = []
            item['containers'] = []
            item['valid'] = False
            item['error'] = str(exc)[-2000:]
        result.append(item)
    return sorted(result, key=lambda p: p['name'])


def preflight(payload):
    working_dir, args = compose_args(payload)
    usage = shutil.disk_usage(working_dir)
    if usage.free < MIN_FREE_BYTES:
        raise RuntimeError(f'Insufficient free space: {format_bytes(usage.free)} available')
    missing = [path for path in payload.get('required_mounts') or [] if not os.path.ismount(path)]
    if missing:
        raise RuntimeError('Required mounts are unavailable: ' + ', '.join(missing))
    run(args + ['config', '--quiet'], cwd=working_dir, timeout=60)
    return working_dir, args


def check_application(payload):
    url = (payload.get('healthcheck_url') or '').strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Health-check URL must be HTTP or HTTPS')
    timeout = bounded_int(payload.get('healthcheck_timeout'), 120, 5, 1800)
    expected_statuses = payload.get('healthcheck_statuses') or []
    try:
        expected_statuses = {int(value) for value in expected_statuses}
    except (TypeError, ValueError) as exc:
        raise ValueError('Health-check statuses must be integers') from exc
    if any(value < 100 or value > 599 for value in expected_statuses):
        raise ValueError('Health-check statuses must be between 100 and 599')
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5, allow_redirects=True)
            healthy = (
                response.status_code in expected_statuses
                if expected_statuses
                else 200 <= response.status_code < 400
            )
            if healthy:
                return {'url': url, 'status_code': response.status_code}
            last_error = f'HTTP {response.status_code}'
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f'Application health check failed: {last_error}')


@app.get('/health')
def health():
    try:
        client().ping()
        return ok(status='ok')
    except Exception as exc:
        return fail(exc, 503)


@app.get('/v1/system')
def system():
    info = client().info()
    disk = shutil.disk_usage('/')
    return ok(system={
        'name': info.get('Name'), 'docker_version': info.get('ServerVersion'),
        'containers': info.get('Containers'), 'containers_running': info.get('ContainersRunning'),
        'images': info.get('Images'), 'cpus': info.get('NCPU'), 'memory': info.get('MemTotal'),
        'disk_free': disk.free, 'disk_free_human': format_bytes(disk.free),
        'agent_time': datetime.now(timezone.utc).isoformat(),
    })


@app.get('/v1/containers')
def containers():
    show_all = request.args.get('all', '0') == '1'
    return ok(containers=[container_info(c) for c in client().containers.list(all=show_all)])


@app.get('/v1/containers/<container_id>')
def container(container_id):
    try:
        return ok(container=container_info(client().containers.get(container_id)))
    except Exception as exc:
        return fail(exc, 404)


@app.get('/v1/containers/<container_id>/stats')
def stats(container_id):
    try:
        return ok(stats=parse_stats(client().containers.get(container_id).stats(stream=False)))
    except Exception as exc:
        return fail(exc, 500)


@app.get('/v1/containers/<container_id>/logs')
def logs(container_id):
    try:
        tail = bounded_int(request.args.get('tail'), 200, 1, 2000)
        raw = client().containers.get(container_id).logs(
            tail=tail, timestamps=request.args.get('timestamps', '1') == '1'
        )
        return ok(logs=raw.decode('utf-8', errors='replace'))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/containers/<container_id>/<action>')
def container_action(container_id, action):
    supported = {'start', 'stop', 'restart', 'remove'}
    if action not in supported:
        return fail('Unsupported action', 404)
    try:
        c = client().containers.get(container_id)
        data = request.get_json(silent=True) or {}
        if action == 'start':
            c.start()
        elif action == 'stop':
            c.stop(timeout=bounded_int(data.get('timeout'), 30, 1, 600))
        elif action == 'restart':
            c.restart(timeout=bounded_int(data.get('timeout'), 30, 1, 600))
        elif action == 'remove':
            c.remove(force=bool(data.get('force')))
        return ok(message=f'Container {c.name} {action} completed')
    except Exception as exc:
        return fail(exc, 500)


@app.get('/v1/images')
def images():
    result = []
    for image in client().images.list():
        attrs = image.attrs
        result.append({
            'id': image.id, 'short_id': image.short_id, 'tags': image.tags,
            'size': attrs.get('Size', 0), 'size_human': format_bytes(attrs.get('Size', 0)),
            'created': attrs.get('Created'), 'repo_digests': attrs.get('RepoDigests') or [],
        })
    return ok(images=result)


@app.post('/v1/images/pull')
def pull_image():
    try:
        ref = (request.get_json(silent=True) or {}).get('image')
        if not ref:
            return fail('Image is required')
        image = client().images.pull(ref)
        return ok(message=f'Pulled {ref}', image_id=image.id)
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/images/<path:image_id>/delete')
def delete_image(image_id):
    try:
        data = request.get_json(silent=True) or {}
        client().images.remove(image_id, force=bool(data.get('force')))
        return ok(message=f'Removed image {image_id}')
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/images/prune')
def prune_images():
    try:
        result = client().images.prune(filters={'dangling': True})
        return ok(images_deleted=result.get('ImagesDeleted') or [], space_reclaimed=result.get('SpaceReclaimed', 0))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/images/prune-volumes')
def prune_volumes():
    try:
        result = client().volumes.prune()
        return ok(volumes_deleted=result.get('VolumesDeleted') or [], space_reclaimed=result.get('SpaceReclaimed', 0))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/images/prune-system')
def prune_system():
    return fail('Full system prune is intentionally unavailable through the agent', 403)


@app.get('/v1/projects')
def projects():
    try:
        return ok(projects=discover())
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/projects/state')
def state():
    try:
        return ok(state=compose_state(request.get_json() or {}))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/projects/action')
def project_action():
    payload = request.get_json() or {}
    action = payload.get('action')
    supported = {'validate', 'start', 'stop', 'restart', 'pull', 'up', 'recreate', 'logs', 'scale', 'down'}
    if action not in supported:
        return fail('Unsupported project action')
    try:
        if action in {'validate', 'start', 'restart', 'pull', 'up', 'recreate', 'scale'}:
            working_dir, args = preflight(payload)
        else:
            working_dir, args = compose_args(payload)
        requested_services = payload.get('services') or []
        if not isinstance(requested_services, list) or not all(
            isinstance(service, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', service)
            for service in requested_services
        ):
            raise ValueError('Invalid Compose service selection')
        services = requested_services
        current_state = compose_state(payload)
        if action in {'pull', 'up', 'recreate'} and not services and current_state.get('containers'):
            services = sorted({
                item.get('Service') for item in current_state['containers']
                if (item.get('State') or '').lower() == 'running' and item.get('Service')
            })
            if not services:
                raise RuntimeError('No running services selected; stopped services will not be started implicitly')
        output = ''
        if action == 'validate':
            command = args + ['config', '--quiet']
        elif action == 'start':
            command = args + ['start'] + services
        elif action == 'stop':
            command = args + ['stop'] + services
        elif action == 'restart':
            command = args + ['restart'] + services
        elif action == 'pull':
            command = args + ['pull'] + services
        elif action == 'up':
            output += run(args + ['pull'] + services, cwd=working_dir, timeout=1500)
            command = args + ['up', '-d', '--wait', '--wait-timeout', str(bounded_int(payload.get('healthcheck_timeout'), 120, 5, 1800))] + services
        elif action == 'recreate':
            output += run(args + ['pull'] + services, cwd=working_dir, timeout=1500)
            command = args + ['up', '-d', '--force-recreate', '--wait', '--wait-timeout', str(bounded_int(payload.get('healthcheck_timeout'), 120, 5, 1800))] + services
        elif action == 'logs':
            command = args + [
                'logs', '--no-color', '--tail',
                str(bounded_int(payload.get('tail'), 200, 1, 2000)),
            ] + services
        elif action == 'scale':
            scales = payload.get('scales') or {}
            if not isinstance(scales, dict) or not all(
                isinstance(service, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', service)
                for service in scales
            ):
                raise ValueError('Invalid Compose scale selection')
            values = [f'{key}={bounded_int(value, 1, 0, 100)}' for key, value in scales.items()]
            command = args + ['up', '-d', '--wait', '--wait-timeout', str(bounded_int(payload.get('healthcheck_timeout'), 120, 5, 1800))] + sum((['--scale', value] for value in values), [])
        else:
            command = args + ['down', '--remove-orphans']
        output += run(command, cwd=working_dir, timeout=1500)
        health = check_application(payload) if action in {'up', 'recreate', 'start', 'restart', 'scale'} else None
        return ok(output=output, healthcheck=health, state=compose_state(payload))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/projects/managed')
def managed_project():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    content = data.get('compose_content') or ''
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,127}', name):
        return fail('Project name must contain lowercase letters, numbers, dots, dashes, or underscores')
    if not content or len(content) > 1024 * 1024:
        return fail('Compose content is empty or too large')
    try:
        directory = allowed_path(os.path.join(MANAGED_ROOT, name), managed_only=True)
        os.makedirs(directory, mode=0o750, exist_ok=True)
        target = os.path.join(directory, 'compose.yaml')
        fd, temporary = tempfile.mkstemp(prefix='.compose-', dir=directory, text=True)
        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o640)
            payload = {'name': name, 'working_dir': directory, 'config_files': [temporary]}
            preflight(payload)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        item = {'name': name, 'working_dir': directory, 'config_files': [target], 'source_type': 'managed'}
        item['config_digest'] = project_digest(item['config_files'])
        return ok(project=item, state=compose_state(item))
    except Exception as exc:
        return fail(exc, 500)


@app.post('/v1/projects/git')
def git_project():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    repo = (data.get('repo_url') or '').strip()
    ref = (data.get('repo_ref') or 'main').strip()
    compose_path = (data.get('compose_path') or 'compose.yaml').strip()
    parsed = urlparse(repo)
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,127}', name):
        return fail('Invalid project name')
    if parsed.scheme not in {'https', 'ssh'} and not repo.startswith('git@'):
        return fail('Repository must use HTTPS or SSH')
    if parsed.password or (parsed.scheme == 'https' and parsed.username):
        return fail('Repository URLs may not contain embedded credentials')
    if not ref or ref.startswith('-') or any(character in ref for character in '\r\n\0'):
        return fail('Invalid Git reference')
    if os.path.isabs(compose_path) or '..' in Path(compose_path).parts:
        return fail('Invalid Compose path')
    try:
        directory = allowed_path(os.path.join(MANAGED_ROOT, name), managed_only=True)
        if os.path.exists(directory) and not os.path.isdir(os.path.join(directory, '.git')):
            raise RuntimeError('Managed project directory already exists and is not a Git checkout')
        os.makedirs(MANAGED_ROOT, mode=0o750, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=f'.{name}-staging-', dir=MANAGED_ROOT)
        try:
            run(['git', 'clone', '--branch', ref, '--single-branch', repo, staging], timeout=300)
            staged_config = allowed_path(os.path.join(staging, compose_path), managed_only=True)
            staged_payload = {
                'name': name,
                'working_dir': staging,
                'config_files': [staged_config],
            }
            preflight(staged_payload)
            source_revision = run(['git', 'rev-parse', 'HEAD'], cwd=staging, timeout=30).strip()
            state = compose_state(staged_payload)

            rollback = None
            if os.path.exists(directory):
                rollback_root = allowed_path(os.path.join(MANAGED_ROOT, 'backups'), managed_only=True)
                os.makedirs(rollback_root, mode=0o700, exist_ok=True)
                rollback = allowed_path(
                    os.path.join(rollback_root, f'{name}-{int(time.time())}'),
                    managed_only=True,
                )
                os.replace(directory, rollback)
            try:
                os.replace(staging, directory)
            except Exception:
                if rollback and not os.path.exists(directory):
                    os.replace(rollback, directory)
                raise

            config_file = allowed_path(os.path.join(directory, compose_path), managed_only=True)
            payload = {'name': name, 'working_dir': directory, 'config_files': [config_file]}
            item = dict(payload, source_type='git', config_digest=state.get('config_digest'))
            return ok(project=item, state=state, source_revision=source_revision)
        finally:
            if os.path.exists(staging):
                shutil.rmtree(staging)
    except Exception as exc:
        return fail(exc, 500)


@app.errorhandler(404)
def not_found(_error):
    return fail('Not found', 404)
