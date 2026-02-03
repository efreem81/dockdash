"""
Container Lifecycle Service - Recreate and Upgrade Containers
Handles container recreation with preserved configuration
"""
from services.docker_service import get_docker_client


def recreate_container(container_id, pull_latest=True):
    """
    Recreate a container with the same configuration but optionally updated image.
    
    Args:
        container_id: ID or name of the container to recreate
        pull_latest: Whether to pull the latest image before recreating
    
    Returns:
        Dictionary with success status and new container info
    """
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    
    try:
        # Get the existing container
        container = client.containers.get(container_id)
        old_name = container.name
        attrs = container.attrs
        config = attrs.get('Config', {})
        host_config = attrs.get('HostConfig', {})
        network_settings = attrs.get('NetworkSettings', {})
        
        # Extract image reference
        image_ref = config.get('Image', '')
        if not image_ref:
            image_ref = container.image.tags[0] if container.image.tags else None
        
        if not image_ref:
            return {'success': False, 'error': 'Cannot determine image for container'}
        
        # Pull latest image if requested
        pulled_new = False
        if pull_latest:
            try:
                old_image_id = container.image.id if container.image else None
                client.images.pull(image_ref)
                new_image = client.images.get(image_ref)
                pulled_new = (new_image.id != old_image_id)
            except Exception as e:
                # Continue even if pull fails - use existing image
                print(f"Warning: Could not pull latest image: {e}")
        
        # Stop and remove the old container
        was_running = container.status == 'running'
        if was_running:
            container.stop(timeout=30)
        container.remove()
        
        # Prepare container configuration
        create_kwargs = _extract_container_config(config, host_config, network_settings)
        create_kwargs['name'] = old_name
        create_kwargs['image'] = image_ref
        
        # Create and optionally start the new container
        new_container = client.containers.create(**create_kwargs)
        
        if was_running:
            new_container.start()
        
        return {
            'success': True,
            'message': f'Container {old_name} recreated successfully',
            'container_id': new_container.short_id,
            'image': image_ref,
            'pulled_new_image': pulled_new,
            'started': was_running
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _extract_container_config(config, host_config, network_settings):
    """Extract container creation parameters from existing container config."""
    kwargs = {}
    
    # Basic config
    if config.get('Cmd'):
        kwargs['command'] = config['Cmd']
    if config.get('Entrypoint'):
        kwargs['entrypoint'] = config['Entrypoint']
    if config.get('Env'):
        kwargs['environment'] = config['Env']
    if config.get('WorkingDir'):
        kwargs['working_dir'] = config['WorkingDir']
    if config.get('User'):
        kwargs['user'] = config['User']
    if config.get('Labels'):
        kwargs['labels'] = config['Labels']
    if config.get('ExposedPorts'):
        kwargs['ports'] = config['ExposedPorts']
    
    # Host config
    if host_config.get('Binds'):
        kwargs['volumes'] = host_config['Binds']
    if host_config.get('PortBindings'):
        kwargs['ports'] = host_config['PortBindings']
    if host_config.get('RestartPolicy'):
        policy = host_config['RestartPolicy']
        kwargs['restart_policy'] = {
            'Name': policy.get('Name', ''),
            'MaximumRetryCount': policy.get('MaximumRetryCount', 0)
        }
    if host_config.get('NetworkMode') and host_config['NetworkMode'] != 'default':
        kwargs['network_mode'] = host_config['NetworkMode']
    if host_config.get('Privileged'):
        kwargs['privileged'] = True
    if host_config.get('CapAdd'):
        kwargs['cap_add'] = host_config['CapAdd']
    if host_config.get('CapDrop'):
        kwargs['cap_drop'] = host_config['CapDrop']
    if host_config.get('Devices'):
        kwargs['devices'] = host_config['Devices']
    if host_config.get('Memory') and host_config['Memory'] > 0:
        kwargs['mem_limit'] = host_config['Memory']
    if host_config.get('CpuShares') and host_config['CpuShares'] > 0:
        kwargs['cpu_shares'] = host_config['CpuShares']
    
    # Detach by default for recreated containers
    kwargs['detach'] = True
    
    return kwargs


def get_container_config(container_id):
    """Get the recreatable configuration for a container."""
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    
    try:
        container = client.containers.get(container_id)
        attrs = container.attrs
        config = attrs.get('Config', {})
        host_config = attrs.get('HostConfig', {})
        
        return {
            'success': True,
            'name': container.name,
            'image': config.get('Image') or (container.image.tags[0] if container.image.tags else 'unknown'),
            'config': _extract_container_config(config, host_config, {}),
            'status': container.status
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}
