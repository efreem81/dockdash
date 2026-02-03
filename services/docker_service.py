"""
Docker Service - Container and Image Management
Handles all Docker/Podman API interactions
"""
import os
import time
import socket
import docker
import requests
from datetime import datetime

# Initialize Docker/Podman client
_docker_client = None

def get_docker_client():
    """Get or create Docker client singleton."""
    global _docker_client
    if _docker_client is None:
        try:
            socket_path = os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock')
            if socket_path.startswith('unix://'):
                _docker_client = docker.DockerClient(base_url=socket_path)
            else:
                _docker_client = docker.from_env()
        except docker.errors.DockerException:
            _docker_client = None
    return _docker_client


def get_host_ip():
    """Get host IP for container URL generation."""
    configured_ip = os.environ.get('HOST_IP')
    if configured_ip:
        return configured_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_container_info(container):
    """Extract comprehensive information from a Docker container."""
    attrs = container.attrs
    state = attrs.get('State', {})
    config = attrs.get('Config', {})
    host_config = attrs.get('HostConfig', {})
    
    # Parse compose labels
    labels = config.get('Labels', {})
    compose_project = labels.get('com.docker.compose.project', '')
    compose_service = labels.get('com.docker.compose.service', '')
    
    # Calculate uptime
    started_at = state.get('StartedAt', '')
    uptime = None
    if started_at and state.get('Running'):
        try:
            start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            uptime = (datetime.now(start_time.tzinfo) - start_time).total_seconds()
        except Exception:
            pass
    
    # Health check status
    health = state.get('Health', {})
    health_status = health.get('Status') if health else None
    
    info = {
        'id': container.short_id,
        'full_id': container.id,
        'name': container.name,
        'status': container.status,
        'image': container.image.tags[0] if container.image.tags else 'unknown',
        'image_id': container.image.short_id if container.image else None,
        'created': attrs['Created'][:19].replace('T', ' '),
        'started_at': started_at[:19].replace('T', ' ') if started_at else None,
        'uptime_seconds': uptime,
        'uptime_human': _format_uptime(uptime) if uptime else None,
        'restart_count': state.get('RestartCount', 0),
        'health_status': health_status,
        'exit_code': state.get('ExitCode'),
        'compose_project': compose_project,
        'compose_service': compose_service,
        'ports': [],
        'urls': [],
        'env_vars': _parse_env_vars(config.get('Env', [])),
        'mounts': _parse_mounts(attrs.get('Mounts', [])),
        'networks': list(attrs.get('NetworkSettings', {}).get('Networks', {}).keys()),
        'labels': labels,
    }
    
    # Get port mappings
    ports = attrs.get('NetworkSettings', {}).get('Ports', {})
    host_ip = get_host_ip()
    seen_host_ports = set()
    
    for container_port, bindings in ports.items():
        if bindings:
            for binding in bindings:
                host_port = binding.get('HostPort')
                if host_port and host_port not in seen_host_ports:
                    seen_host_ports.add(host_port)
                    port_info = {
                        'container_port': container_port,
                        'host_port': host_port,
                        'url': f"http://{host_ip}:{host_port}",
                        'host_ip': host_ip
                    }
                    info['ports'].append(port_info)
                    info['urls'].append(port_info['url'])
    
    return info


def _format_uptime(seconds):
    """Format uptime seconds to human readable string."""
    if seconds is None:
        return None
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _parse_env_vars(env_list):
    """Parse environment variables, hiding sensitive values."""
    sensitive_keys = {'password', 'secret', 'key', 'token', 'api_key', 'apikey'}
    result = {}
    for env in env_list or []:
        if '=' in env:
            key, value = env.split('=', 1)
            if any(s in key.lower() for s in sensitive_keys):
                result[key] = '********'
            else:
                result[key] = value
    return result


def _parse_mounts(mounts):
    """Parse mount information."""
    return [{
        'type': m.get('Type'),
        'source': m.get('Source'),
        'destination': m.get('Destination'),
        'mode': m.get('Mode'),
        'rw': m.get('RW')
    } for m in mounts or []]


def get_all_containers(show_all=False):
    """Get all Docker containers."""
    client = get_docker_client()
    if not client:
        return []
    try:
        containers = client.containers.list(all=show_all)
        return [get_container_info(c) for c in containers]
    except Exception as e:
        print(f"Error getting containers: {e}")
        return []


def get_container_stats(container_id):
    """Get real-time stats for a container."""
    client = get_docker_client()
    if not client:
        return None
    try:
        container = client.containers.get(container_id)
        stats = container.stats(stream=False)
        return _parse_stats(stats)
    except Exception as e:
        return {'error': str(e)}


def _parse_stats(stats):
    """Parse container stats into readable format."""
    # CPU usage
    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                stats['precpu_stats']['cpu_usage']['total_usage']
    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                   stats['precpu_stats']['system_cpu_usage']
    cpu_count = stats['cpu_stats'].get('online_cpus', 1)
    cpu_percent = (cpu_delta / system_delta) * cpu_count * 100 if system_delta > 0 else 0
    
    # Memory usage
    mem_usage = stats['memory_stats'].get('usage', 0)
    mem_limit = stats['memory_stats'].get('limit', 1)
    mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
    
    # Network I/O
    networks = stats.get('networks', {})
    net_rx = sum(n.get('rx_bytes', 0) for n in networks.values())
    net_tx = sum(n.get('tx_bytes', 0) for n in networks.values())
    
    # Block I/O
    blk_stats = stats.get('blkio_stats', {}).get('io_service_bytes_recursive', []) or []
    blk_read = sum(s['value'] for s in blk_stats if s.get('op') == 'read')
    blk_write = sum(s['value'] for s in blk_stats if s.get('op') == 'write')
    
    return {
        'cpu_percent': round(cpu_percent, 2),
        'memory_usage': mem_usage,
        'memory_limit': mem_limit,
        'memory_percent': round(mem_percent, 2),
        'memory_usage_human': _format_bytes(mem_usage),
        'memory_limit_human': _format_bytes(mem_limit),
        'network_rx': net_rx,
        'network_tx': net_tx,
        'network_rx_human': _format_bytes(net_rx),
        'network_tx_human': _format_bytes(net_tx),
        'block_read': blk_read,
        'block_write': blk_write,
        'block_read_human': _format_bytes(blk_read),
        'block_write_human': _format_bytes(blk_write),
    }


def _format_bytes(size):
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def exec_container(container_id, command, workdir=None):
    """Execute a command in a container."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        container = client.containers.get(container_id)
        result = container.exec_run(command, workdir=workdir, demux=True)
        stdout, stderr = result.output
        return {
            'success': True,
            'exit_code': result.exit_code,
            'stdout': stdout.decode('utf-8', errors='replace') if stdout else '',
            'stderr': stderr.decode('utf-8', errors='replace') if stderr else ''
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def remove_container(container_id, force=False):
    """Remove a container."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        container = client.containers.get(container_id)
        name = container.name
        container.remove(force=force)
        return {'success': True, 'message': f'Container {name} removed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def prune_containers():
    """Remove all stopped containers."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        result = client.containers.prune()
        return {
            'success': True,
            'containers_deleted': result.get('ContainersDeleted', []),
            'space_reclaimed': result.get('SpaceReclaimed', 0),
            'space_reclaimed_human': _format_bytes(result.get('SpaceReclaimed', 0))
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

