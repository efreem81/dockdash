"""
Container Lifecycle Service - Recreate and Upgrade Containers
Handles container recreation with preserved configuration
"""
import logging
import time
from services.docker_service import get_docker_client

logger = logging.getLogger(__name__)


def _parse_bind_target(bind_spec: str) -> str | None:
    """Return the container-path target from a bind spec like 'src:target:mode'."""
    if not bind_spec or ':' not in bind_spec:
        return None
    parts = bind_spec.split(':')
    if len(parts) < 2:
        return None
    return parts[1] or None


def _build_container_ports(config: dict, host_config: dict):
    exposed = (config or {}).get('ExposedPorts') or {}
    if exposed:
        return list(exposed.keys())
    port_bindings = (host_config or {}).get('PortBindings') or {}
    if port_bindings:
        return list(port_bindings.keys())
    return None


def _build_container_volumes(config: dict, host_config: dict):
    volumes: set[str] = set()
    cfg_vols = (config or {}).get('Volumes') or {}
    for v in cfg_vols.keys():
        if v:
            volumes.add(v)
    for bind in (host_config or {}).get('Binds') or []:
        target = _parse_bind_target(bind)
        if target:
            volumes.add(target)
    return sorted(volumes) if volumes else None


def _build_host_config(client, host_config: dict, primary_network: str | None):
    api = client.api
    hc = host_config or {}

    restart_policy = hc.get('RestartPolicy')
    if isinstance(restart_policy, dict):
        restart_policy = {
            'Name': restart_policy.get('Name', ''),
            'MaximumRetryCount': restart_policy.get('MaximumRetryCount', 0)
        }
    else:
        restart_policy = None

    network_mode = hc.get('NetworkMode')
    if primary_network and primary_network not in ('bridge', 'host', 'none', 'default'):
        if not (isinstance(network_mode, str) and network_mode.startswith('container:')):
            network_mode = primary_network
    if network_mode == 'default':
        network_mode = None

    return api.create_host_config(
        binds=hc.get('Binds'),
        port_bindings=hc.get('PortBindings'),
        restart_policy=restart_policy,
        network_mode=network_mode,
        privileged=bool(hc.get('Privileged')),
        cap_add=hc.get('CapAdd'),
        cap_drop=hc.get('CapDrop'),
        devices=hc.get('Devices'),
        mem_limit=hc.get('Memory') if hc.get('Memory', 0) and hc.get('Memory', 0) > 0 else None,
        cpu_shares=hc.get('CpuShares') if hc.get('CpuShares', 0) and hc.get('CpuShares', 0) > 0 else None,
        extra_hosts=hc.get('ExtraHosts'),
        dns=hc.get('Dns'),
        dns_search=hc.get('DnsSearch'),
        links=hc.get('Links'),
        volumes_from=hc.get('VolumesFrom'),
        security_opt=hc.get('SecurityOpt'),
        read_only=bool(hc.get('ReadonlyRootfs')) if hc.get('ReadonlyRootfs') is not None else None,
        tmpfs=hc.get('Tmpfs'),
        ipc_mode=hc.get('IpcMode') or None,
        pid_mode=hc.get('PidMode') or None,
        userns_mode=hc.get('UsernsMode') or None,
        init=hc.get('Init') if 'Init' in hc else None,
        auto_remove=bool(hc.get('AutoRemove')) if 'AutoRemove' in hc else None,
        log_config=hc.get('LogConfig') or None,
        shm_size=hc.get('ShmSize') or None,
        ulimits=hc.get('Ulimits') or None,
    )


def _resolve_container_network_mode(client, network_mode: str | None) -> str | None:
    if not network_mode or not isinstance(network_mode, str):
        return network_mode
    if not network_mode.startswith('container:'):
        return network_mode

    ref = network_mode.split(':', 1)[1]
    if not ref:
        return network_mode

    try:
        target = client.containers.get(ref)
        return f"container:{target.name}"
    except Exception:
        return network_mode


def _build_networking_config(client, networks: dict, primary_network: str | None):
    if not networks:
        return None, None

    api = client.api

    # Pick a primary network that exists in NetworkSettings.Networks
    primary = None
    if primary_network and primary_network in networks:
        primary = primary_network
    else:
        primary = next(iter(networks.keys()))

    net_cfg = networks.get(primary) or {}
    endpoint = api.create_endpoint_config(
        aliases=net_cfg.get('Aliases'),
        links=net_cfg.get('Links'),
        ipv4_address=net_cfg.get('IPAddress') or None,
        ipv6_address=net_cfg.get('GlobalIPv6Address') or None,
    )
    networking_config = api.create_networking_config({primary: endpoint})
    return networking_config, primary


def _connect_additional_networks(client, container, networks: dict, primary: str | None):
    for net_name, net_cfg in (networks or {}).items():
        if primary and net_name == primary:
            continue
        try:
            client.networks.get(net_name).connect(
                container,
                aliases=net_cfg.get('Aliases'),
                ipv4_address=net_cfg.get('IPAddress') or None,
                ipv6_address=net_cfg.get('GlobalIPv6Address') or None,
            )
        except Exception as e:
            print(f"Warning: Could not connect {container.name} to network {net_name}: {e}")


def _wait_for_running(container, timeout_seconds: float = 6.0) -> bool:
    import time
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            container.reload()
            if container.status == 'running':
                return True
            # If it already exited, don't keep waiting.
            state = (container.attrs or {}).get('State') or {}
            if state.get('Status') in ('exited', 'dead'):
                return False
        except Exception:
            pass
        time.sleep(0.5)
    try:
        container.reload()
        return container.status == 'running'
    except Exception:
        return False


def recreate_container(container_id, pull_latest=True, skip_scan=False):
    """
    Recreate a container with the same configuration but optionally updated image.
    
    Args:
        container_id: ID or name of the container to recreate
        pull_latest: Whether to pull the latest image before recreating
        skip_scan: Whether to skip vulnerability scanning (useful for batch updates)
    
    Returns:
        Dictionary with success status and new container info
    """
    client = get_docker_client()
    if not client:
        return {'success': False, 'error': 'Docker not available'}
    
    try:
        # Get the existing container
        container = client.containers.get(container_id)
        try:
            container.reload()
        except Exception:
            pass
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
                logger.warning('Could not pull latest image for %s: %s', image_ref, e)
        
        # Recreate in a rollback-safe way:
        # 1) rename old container to free the name
        # 2) stop old container to free ports
        # 3) create + start new
        # 4) on failure, remove new and restore old (rename back + restart)
        was_running = container.status == 'running'
        logger.info('Recreating container %s: was_running=%s pull_latest=%s', old_name, was_running, pull_latest)

        old_container = container
        original_name = old_name
        rollback_name = f"{original_name}__dockdash_old_{int(time.time())}"

        renamed_old = False
        new_container = None
        started = False

        try:
            old_container.rename(rollback_name)
            renamed_old = True
        except Exception as e:
            return {'success': False, 'error': f'Failed to rename existing container {original_name}: {e}'}

        try:
            if was_running:
                old_container.stop(timeout=30)

            networks = (network_settings or {}).get('Networks') or {}
            primary_network_mode = (host_config or {}).get('NetworkMode')
            primary_network_mode = _resolve_container_network_mode(client, primary_network_mode)
            networking_config, primary_network = _build_networking_config(client, networks, primary_network_mode)
            host_cfg_source = dict(host_config or {})
            if primary_network_mode:
                host_cfg_source['NetworkMode'] = primary_network_mode
            host_cfg_obj = _build_host_config(client, host_cfg_source, primary_network)

            ports = _build_container_ports(config, host_config)
            volumes = _build_container_volumes(config, host_config)

            created = client.api.create_container(
                image=image_ref,
                name=original_name,
                command=config.get('Cmd') or None,
                entrypoint=config.get('Entrypoint') or None,
                environment=config.get('Env') or None,
                working_dir=config.get('WorkingDir') or None,
                user=config.get('User') or None,
                labels=config.get('Labels') or None,
                hostname=config.get('Hostname') or None,
                domainname=config.get('Domainname') or None,
                stop_signal=config.get('StopSignal') or None,
                healthcheck=config.get('Healthcheck') or None,
                tty=bool(config.get('Tty')),
                stdin_open=bool(config.get('OpenStdin')),
                ports=ports,
                volumes=volumes,
                host_config=host_cfg_obj,
                networking_config=networking_config,
            )

            new_id = created.get('Id')
            new_container = client.containers.get(new_id)
            logger.debug('Created new container %s for %s', new_container.short_id, original_name)

            # Attach to any additional networks
            _connect_additional_networks(client, new_container, networks, primary_network)

            if was_running:
                new_container.start()
                started = _wait_for_running(new_container, timeout_seconds=6.0)
                if started:
                    logger.info('Started container %s successfully', original_name)
                else:
                    try:
                        new_container.reload()
                        state = (new_container.attrs or {}).get('State') or {}
                        exit_code = state.get('ExitCode')
                        status = state.get('Status')
                        err = state.get('Error')
                        try:
                            last_logs = new_container.logs(tail=80).decode('utf-8', errors='ignore')
                        except Exception:
                            last_logs = None
                        log_hint = f"; logs_tail=\n{last_logs}" if last_logs else ""
                        raise RuntimeError(
                            f"Container did not stay running (status={status}, exit_code={exit_code}, error={err}){log_hint}"
                        )
                    except Exception as start_error:
                        raise start_error

            # If we got here, creation (and optional start) succeeded.
            try:
                old_container.remove(v=True, force=False)
            except Exception as e:
                logger.warning('Could not remove old container %s: %s', rollback_name, e)

        except Exception as e:
            # Rollback
            rollback_error = str(e)
            logger.warning('Recreate failed for %s, rolling back: %s', original_name, rollback_error)
            try:
                if new_container is not None:
                    try:
                        new_container.remove(v=False, force=True)
                    except Exception:
                        pass
            finally:
                try:
                    if renamed_old:
                        old_container.rename(original_name)
                    if was_running:
                        old_container.start()
                except Exception as re:
                    rollback_error = f"{rollback_error}; rollback_failed={re}"
            return {'success': False, 'error': rollback_error}
        
        # Scan the image after recreation unless skip_scan=True (batch updates)
        scan_result = None
        if not skip_scan:
            try:
                from services.vulnerability_service import scan_image, save_scan_result, clear_image_cache
                # Clear cache to force fresh scan of the (potentially new) image
                clear_image_cache(image_ref)
                start_time = time.time()
                scan_result = scan_image(image_ref, 'CRITICAL,HIGH,MEDIUM,LOW')
                duration = time.time() - start_time
                save_scan_result(image_ref, scan_result, duration)
            except Exception as e:
                logger.warning('Could not scan image %s: %s', image_ref, e)
        
        return {
            'success': True,
            'message': f'Container {old_name} recreated successfully',
            'container_id': new_container.short_id,
            'image': image_ref,
            'pulled_new_image': pulled_new,
            'started': started,
            'vulnerability_scan': scan_result.get('summary') if scan_result and scan_result.get('success') else None
        }
        
    except Exception as e:
        logger.exception('recreate_container failed for %s: %s', container_id, e)
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
