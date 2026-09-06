"""Endpoint-aware facade for Docker container and image operations."""
from __future__ import annotations

from datetime import datetime

from flask import request, session

from config import db
from models import Endpoint
from services.agent_client import AgentClient, AgentError
from services import docker_service, image_service


class EndpointSelectionError(LookupError):
    """Raised when an explicitly selected endpoint cannot be used safely."""


def get_endpoint(endpoint_id=None, remember=False):
    explicit = endpoint_id is not None
    raw = endpoint_id
    if not explicit and 'endpoint_id' in request.args:
        raw = request.args.get('endpoint_id')
        explicit = True
    if not explicit and request.headers.get('X-DockDash-Endpoint') is not None:
        raw = request.headers.get('X-DockDash-Endpoint')
        explicit = True
    if not explicit:
        raw = session.get('endpoint_id')
    endpoint = None
    if raw is not None:
        try:
            endpoint = db.session.get(Endpoint, int(raw))
        except (TypeError, ValueError) as exc:
            if explicit:
                raise EndpointSelectionError('Invalid Docker endpoint identifier') from exc
    if explicit and endpoint is None:
        raise EndpointSelectionError('Docker endpoint was not found')
    if endpoint is not None and not endpoint.enabled:
        if explicit:
            raise EndpointSelectionError('Docker endpoint is disabled')
        session.pop('endpoint_id', None)
        endpoint = None
    if endpoint is None:
        endpoint = Endpoint.query.filter_by(enabled=True).order_by(Endpoint.id).first()
    if endpoint is None:
        raise RuntimeError('No Docker endpoint is configured')
    if remember:
        session['endpoint_id'] = endpoint.id
    return endpoint


def _agent(endpoint):
    return AgentClient(endpoint)


def mark_success(endpoint):
    endpoint.last_seen = datetime.utcnow()
    endpoint.last_error = None
    db.session.commit()


def mark_failure(endpoint, error):
    endpoint.last_error = str(error)[:2000]
    db.session.commit()


def endpoint_health(endpoint):
    try:
        if endpoint.kind == 'local':
            client = docker_service.get_docker_client()
            if not client:
                raise RuntimeError('Docker socket is unavailable')
            info = client.info()
            payload = {
                'success': True,
                'system': {
                    'name': info.get('Name'),
                    'docker_version': info.get('ServerVersion'),
                    'containers': info.get('Containers'),
                    'containers_running': info.get('ContainersRunning'),
                    'images': info.get('Images'),
                },
            }
        else:
            payload = _agent(endpoint).get('/v1/system')
        mark_success(endpoint)
        return payload
    except Exception as exc:
        mark_failure(endpoint, exc)
        raise


def list_containers(endpoint, show_all=False):
    if endpoint.kind == 'local':
        return docker_service.get_all_containers(show_all=show_all)
    payload = _agent(endpoint).get('/v1/containers', params={'all': '1' if show_all else '0'})
    mark_success(endpoint)
    return payload.get('containers', [])


def container_detail(endpoint, container_id):
    if endpoint.kind == 'local':
        client = docker_service.get_docker_client()
        return docker_service.get_container_info(client.containers.get(container_id))
    return _agent(endpoint).get(f'/v1/containers/{container_id}').get('container')


def container_stats(endpoint, container_id):
    if endpoint.kind == 'local':
        return docker_service.get_container_stats(container_id)
    return _agent(endpoint).get(f'/v1/containers/{container_id}/stats').get('stats')


def container_logs(endpoint, container_id, tail=200, timestamps=True):
    if endpoint.kind == 'local':
        client = docker_service.get_docker_client()
        container = client.containers.get(container_id)
        raw = container.logs(tail=tail, timestamps=timestamps)
        return raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
    return _agent(endpoint).get(
        f'/v1/containers/{container_id}/logs',
        params={'tail': tail, 'timestamps': '1' if timestamps else '0'},
    ).get('logs', '')


def container_action(endpoint, container_id, action, data=None):
    if endpoint.kind == 'agent':
        if action == 'exec':
            raise AgentError('Remote container exec is intentionally unavailable')
        return _agent(endpoint).post(f'/v1/containers/{container_id}/{action}', json=data or {})
    client = docker_service.get_docker_client()
    container = client.containers.get(container_id)
    if action == 'start':
        container.start()
    elif action == 'stop':
        container.stop()
    elif action == 'restart':
        container.restart()
    elif action == 'remove':
        container.remove(force=bool((data or {}).get('force')))
    elif action == 'exec':
        return docker_service.exec_container(container_id, (data or {}).get('command'), (data or {}).get('workdir'))
    else:
        raise ValueError(f'Unsupported container action: {action}')
    return {'success': True, 'message': f'Container {container.name} {action} completed'}


def list_images(endpoint):
    if endpoint.kind == 'local':
        return image_service.list_images()
    return _agent(endpoint).get('/v1/images').get('images', [])


def image_action(endpoint, action, data=None, image_id=None):
    data = data or {}
    if endpoint.kind == 'agent':
        path = f'/v1/images/{image_id}/{action}' if image_id else f'/v1/images/{action}'
        return _agent(endpoint).post(path, json=data, timeout=600)
    if action == 'pull':
        return image_service.pull_image(data.get('image'))
    if action == 'delete':
        return image_service.delete_image(image_id, force=bool(data.get('force')))
    if action == 'prune':
        return image_service.prune_images(dangling_only=bool(data.get('dangling_only', True)))
    if action == 'prune-volumes':
        return image_service.prune_volumes()
    if action == 'prune-system':
        return image_service.prune_all()
    raise ValueError(f'Unsupported image action: {action}')
