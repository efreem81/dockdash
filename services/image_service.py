"""
Image Service - Docker Image Management
Handles image listing, pulling, pruning, and update detection
"""
import time
import requests
from services.docker_service import get_docker_client, _format_bytes

# Cache for update checks
_cache = {}


def _cache_get(key, ttl_seconds):
    entry = _cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if (time.time() - ts) > ttl_seconds:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _cache[key] = (time.time(), value)


def list_images():
    """List all Docker images."""
    client = get_docker_client()
    if not client:
        return []
    try:
        images = client.images.list()
        return [{
            'id': img.short_id,
            'full_id': img.id,
            'tags': img.tags,
            'size': img.attrs.get('Size', 0),
            'size_human': _format_bytes(img.attrs.get('Size', 0)),
            'created': img.attrs.get('Created', '')[:19].replace('T', ' '),
            'repo_digests': img.attrs.get('RepoDigests', []),
        } for img in images]
    except Exception as e:
        return {'error': str(e)}


def get_image_details(image_id):
    """Get detailed information about an image."""
    client = get_docker_client()
    if not client:
        return None
    try:
        image = client.images.get(image_id)
        return {
            'id': image.short_id,
            'full_id': image.id,
            'tags': image.tags,
            'size': image.attrs.get('Size', 0),
            'size_human': _format_bytes(image.attrs.get('Size', 0)),
            'created': image.attrs.get('Created', ''),
            'architecture': image.attrs.get('Architecture', ''),
            'os': image.attrs.get('Os', ''),
            'repo_digests': image.attrs.get('RepoDigests', []),
            'labels': image.attrs.get('Config', {}).get('Labels', {}),
        }
    except Exception as e:
        return {'error': str(e)}


def pull_image(image_ref):
    """Pull an image from registry."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        image = client.images.pull(image_ref)
        return {
            'success': True,
            'id': image.short_id,
            'tags': image.tags,
            'message': f'Successfully pulled {image_ref}'
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def delete_image(image_id, force=False):
    """Delete an image."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        client.images.remove(image_id, force=force)
        return {'success': True, 'message': f'Image {image_id} deleted'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def prune_images(dangling_only=True):
    """Remove unused images."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        filters = {'dangling': True} if dangling_only else {}
        result = client.images.prune(filters=filters)
        return {
            'success': True,
            'images_deleted': result.get('ImagesDeleted', []),
            'space_reclaimed': result.get('SpaceReclaimed', 0),
            'space_reclaimed_human': _format_bytes(result.get('SpaceReclaimed', 0))
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def prune_volumes():
    """Remove unused volumes."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    try:
        result = client.volumes.prune()
        return {
            'success': True,
            'volumes_deleted': result.get('VolumesDeleted', []),
            'space_reclaimed': result.get('SpaceReclaimed', 0),
            'space_reclaimed_human': _format_bytes(result.get('SpaceReclaimed', 0))
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def prune_all():
    """Prune containers, images, and volumes."""
    results = {
        'containers': {},
        'images': {},
        'volumes': {},
        'total_space_reclaimed': 0
    }
    
    from services.docker_service import prune_containers
    results['containers'] = prune_containers()
    results['images'] = prune_images(dangling_only=False)
    results['volumes'] = prune_volumes()
    
    total = 0
    for key in ['containers', 'images', 'volumes']:
        if isinstance(results[key], dict):
            total += results[key].get('space_reclaimed', 0)
    
    results['total_space_reclaimed'] = total
    results['total_space_reclaimed_human'] = _format_bytes(total)
    results['success'] = True
    
    return results


def parse_image_reference(image_ref):
    """Parse a Docker image reference into components."""
    result = {
        'registry': 'docker.io',
        'namespace': 'library',
        'repo': '',
        'tag': 'latest',
        'original': image_ref
    }
    
    if not image_ref or image_ref == 'unknown':
        return result
    
    if '@sha256:' in image_ref:
        image_ref, digest = image_ref.split('@', 1)
        result['digest'] = digest
        result['tag'] = None
    elif ':' in image_ref.split('/')[-1]:
        image_ref, result['tag'] = image_ref.rsplit(':', 1)
    
    parts = image_ref.split('/')
    
    if len(parts) == 1:
        result['repo'] = parts[0]
    elif len(parts) == 2:
        if '.' in parts[0] or ':' in parts[0]:
            result['registry'] = parts[0]
            result['repo'] = parts[1]
        else:
            result['namespace'] = parts[0]
            result['repo'] = parts[1]
    else:
        result['registry'] = parts[0]
        result['namespace'] = parts[1]
        result['repo'] = '/'.join(parts[2:])
    
    return result


def get_local_image_digest(image_ref):
    """Get the digest of a local image."""
    client = get_docker_client()
    if not client:
        return None
    try:
        image = client.images.get(image_ref)
        digests = image.attrs.get('RepoDigests', [])
        if digests:
            for d in digests:
                if '@' in d:
                    return d.split('@')[1]
        return image.id
    except Exception:
        return None


def get_remote_image_digest(parsed):
    """Get the digest of a remote image from the registry."""
    registry = parsed['registry']
    namespace = parsed['namespace']
    repo = parsed['repo']
    tag = parsed.get('tag') or 'latest'
    
    if not repo:
        return None
    
    try:
        if registry in ('docker.io', 'registry.hub.docker.com', 'index.docker.io'):
            token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{namespace}/{repo}:pull"
            token_resp = requests.get(token_url, timeout=5)
            if token_resp.status_code != 200:
                return None
            token = token_resp.json().get('token')
            
            manifest_url = f"https://registry-1.docker.io/v2/{namespace}/{repo}/manifests/{tag}"
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'
            }
            resp = requests.head(manifest_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return resp.headers.get('Docker-Content-Digest')
        
        elif registry == 'ghcr.io':
            manifest_url = f"https://ghcr.io/v2/{namespace}/{repo}/manifests/{tag}"
            headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
            resp = requests.head(manifest_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return resp.headers.get('Docker-Content-Digest')
    except Exception as e:
        print(f"Error checking remote digest for {parsed['original']}: {e}")
    
    return None


def check_image_update(image_ref):
    """Check if an image has an update available."""
    result = {
        'image': image_ref,
        'has_update': None,
        'local_digest': None,
        'remote_digest': None,
        'error': None
    }
    
    if not image_ref or image_ref == 'unknown':
        result['error'] = 'Invalid image reference'
        return result
    
    parsed = parse_image_reference(image_ref)
    
    if parsed.get('digest'):
        result['error'] = 'Image specified by digest (immutable)'
        return result
    
    cache_key = f"update:{image_ref}"
    cached = _cache_get(cache_key, ttl_seconds=300)
    if cached:
        return cached
    
    local_digest = get_local_image_digest(image_ref)
    result['local_digest'] = local_digest
    
    if not local_digest:
        result['error'] = 'Could not get local image digest'
        return result
    
    remote_digest = get_remote_image_digest(parsed)
    result['remote_digest'] = remote_digest
    
    if not remote_digest:
        result['error'] = 'Could not fetch remote digest'
        return result
    
    result['has_update'] = (local_digest != remote_digest)
    _cache_set(cache_key, result)
    return result
