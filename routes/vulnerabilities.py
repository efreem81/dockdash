"""
Vulnerability API Routes
Image security scanning endpoints
"""
import time

from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.vulnerability_service import (
    scan_image, scan_multiple_images,
    get_vulnerability_report, clear_cache, scan_all_container_images,
    get_stored_vulnerabilities, get_scan_status, get_scan_settings,
    update_scan_settings, scan_container_image, save_scan_result,
    get_image_vulnerability_details,
)
from services.fleet_service import (
    get_endpoint, scan_endpoint_images, vulnerability_status,
    container_detail as fleet_container_detail,
)

vulnerabilities_bp = Blueprint('vulnerabilities', __name__)


@vulnerabilities_bp.route('/vulnerabilities/status')
@login_required
def api_scanner_status():
    """Check if vulnerability scanner is available."""
    endpoint = get_endpoint()
    try:
        status = vulnerability_status(endpoint)
        available = bool(status.get('available'))
        return jsonify({
            'success': True,
            'scanner': 'trivy',
            'available': available,
            'version': status.get('version'),
            'message': 'Trivy scanner is ready' if available else 'Trivy not installed',
            'settings': get_scan_settings(),
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502


@vulnerabilities_bp.route('/vulnerabilities/scan')
@login_required
def api_scan_image():
    """Scan a single image for vulnerabilities."""
    endpoint = get_endpoint()
    image = (request.args.get('image') or '').strip()
    severity = request.args.get('severity', 'CRITICAL,HIGH')

    if not image:
        return jsonify({'success': False, 'error': 'Image parameter required'}), 400

    started = time.time()
    try:
        result = (
            scan_endpoint_images(endpoint, image=image, severity=severity)
            if endpoint.kind == 'agent'
            else scan_image(image, severity)
        )
        save_scan_result(image, result, time.time() - started, endpoint_id=endpoint.id)
        return jsonify(result)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502


@vulnerabilities_bp.route('/vulnerabilities/scan', methods=['POST'])
@login_required
def api_scan_images():
    """Scan multiple images for vulnerabilities."""
    endpoint = get_endpoint()
    data = request.get_json() or {}
    images = data.get('images', [])
    severity = data.get('severity', 'CRITICAL,HIGH')

    if not images or not isinstance(images, list):
        return jsonify({'success': False, 'error': 'images array required'}), 400

    try:
        result = (
            scan_endpoint_images(endpoint, images=images, severity=severity)
            if endpoint.kind == 'agent'
            else scan_multiple_images(images, severity)
        )
        for image_ref, scan_result in result.get('results', {}).items():
            save_scan_result(image_ref, scan_result, endpoint_id=endpoint.id)
        return jsonify(result)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502


@vulnerabilities_bp.route('/vulnerabilities/report/<path:image_ref>')
@login_required
def api_vulnerability_report(image_ref):
    """Get a detailed vulnerability report for an image."""
    endpoint = get_endpoint()
    if endpoint.kind == 'local':
        return jsonify(get_vulnerability_report(image_ref))
    try:
        return jsonify(scan_endpoint_images(endpoint, image=image_ref))
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502


@vulnerabilities_bp.route('/vulnerabilities/details/<path:image_ref>')
@login_required
def api_vulnerability_details(image_ref):
    """Get full vulnerability details (CVE list) for an image from stored data."""
    try:
        endpoint = get_endpoint()
        result = get_image_vulnerability_details(image_ref, endpoint_id=endpoint.id)
        if not result:
            return jsonify({
                'success': False,
                'error': 'No scan data found for this image. Run a security scan first.'
            }), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@vulnerabilities_bp.route('/vulnerabilities/cache/clear', methods=['POST'])
@login_required
def api_clear_cache():
    """Clear the vulnerability scan cache."""
    result = clear_cache()
    return jsonify(result)


@vulnerabilities_bp.route('/vulnerabilities/scan-all', methods=['POST'])
@login_required
def api_scan_all_images():
    """Scan all container images for vulnerabilities."""
    try:
        endpoint = get_endpoint()
        data = request.get_json(silent=True) or {}
        severity = data.get('severity')  # Use settings default if not provided
        if endpoint.kind == 'agent':
            result = scan_endpoint_images(endpoint, severity=severity, scan_all=True)
            for image_ref, scan_result in result.get('results', {}).items():
                save_scan_result(image_ref, scan_result, endpoint_id=endpoint.id)
        else:
            result = scan_all_container_images(severity, endpoint_id=endpoint.id)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@vulnerabilities_bp.route('/vulnerabilities/results')
@login_required
def api_get_all_results():
    """Get all stored vulnerability scan results."""
    endpoint = get_endpoint()
    results = get_stored_vulnerabilities(endpoint_id=endpoint.id)
    return jsonify({
        'success': True,
        'results': results,
        'count': len(results)
    })


@vulnerabilities_bp.route('/vulnerabilities/progress')
@login_required
def api_scan_progress():
    """Get current scan progress."""
    status = get_scan_status()
    return jsonify({'success': True, **status})


@vulnerabilities_bp.route('/vulnerabilities/settings', methods=['GET'])
@login_required
def api_get_scan_settings():
    """Get vulnerability scan settings."""
    settings = get_scan_settings()
    return jsonify({'success': True, 'settings': settings})


@vulnerabilities_bp.route('/vulnerabilities/settings', methods=['POST'])
@login_required
def api_update_scan_settings():
    """Update vulnerability scan settings."""
    data = request.get_json() or {}

    result = update_scan_settings(
        enabled=data.get('enabled'),
        schedule_type=data.get('schedule_type'),
        schedule_hour=data.get('schedule_hour'),
        schedule_minute=data.get('schedule_minute'),
        schedule_day=data.get('schedule_day'),
        severity_filter=data.get('severity_filter'),
        log_level=data.get('log_level')
    )
    return jsonify(result)


@vulnerabilities_bp.route('/vulnerabilities/scan-container/<container_id>', methods=['POST'])
@login_required
def api_scan_container(container_id):
    """Scan a specific container's image for vulnerabilities."""
    endpoint = get_endpoint()
    data = request.get_json() or {}
    force = data.get('force', True)  # Force fresh scan by default
    if endpoint.kind == 'local':
        return jsonify(scan_container_image(
            container_id,
            force=force,
            endpoint_id=endpoint.id,
        ))
    try:
        container = fleet_container_detail(endpoint, container_id)
        image_ref = container.get('image')
        started = time.time()
        scan_result = scan_endpoint_images(endpoint, image=image_ref)
        save_scan_result(
            image_ref,
            scan_result,
            time.time() - started,
            endpoint_id=endpoint.id,
        )
        return jsonify({
            'success': scan_result.get('success', False),
            'container_id': container_id,
            'container_name': container.get('name'),
            'image': image_ref,
            'scan_result': scan_result.get('summary'),
            'error': scan_result.get('error'),
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
