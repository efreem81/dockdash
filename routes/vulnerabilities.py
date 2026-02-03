"""
Vulnerability API Routes
Image security scanning endpoints
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.vulnerability_service import (
    is_trivy_available, scan_image, scan_multiple_images,
    get_vulnerability_report, clear_cache, scan_all_container_images,
    get_stored_vulnerabilities, get_scan_status, get_scan_settings,
    update_scan_settings, scan_container_image
)

vulnerabilities_bp = Blueprint('vulnerabilities', __name__)


@vulnerabilities_bp.route('/vulnerabilities/status')
@login_required
def api_scanner_status():
    """Check if vulnerability scanner is available."""
    available = is_trivy_available()
    settings = get_scan_settings()
    return jsonify({
        'success': True,
        'scanner': 'trivy',
        'available': available,
        'message': 'Trivy scanner is ready' if available else 'Trivy not installed',
        'settings': settings
    })


@vulnerabilities_bp.route('/vulnerabilities/scan')
@login_required
def api_scan_image():
    """Scan a single image for vulnerabilities."""
    image = (request.args.get('image') or '').strip()
    severity = request.args.get('severity', 'CRITICAL,HIGH')
    
    if not image:
        return jsonify({'success': False, 'error': 'Image parameter required'}), 400
    
    result = scan_image(image, severity)
    return jsonify(result)


@vulnerabilities_bp.route('/vulnerabilities/scan', methods=['POST'])
@login_required
def api_scan_images():
    """Scan multiple images for vulnerabilities."""
    data = request.get_json() or {}
    images = data.get('images', [])
    severity = data.get('severity', 'CRITICAL,HIGH')
    
    if not images or not isinstance(images, list):
        return jsonify({'success': False, 'error': 'images array required'}), 400
    
    result = scan_multiple_images(images, severity)
    return jsonify(result)


@vulnerabilities_bp.route('/vulnerabilities/report/<path:image_ref>')
@login_required
def api_vulnerability_report(image_ref):
    """Get a detailed vulnerability report for an image."""
    result = get_vulnerability_report(image_ref)
    return jsonify(result)


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
        data = request.get_json(silent=True) or {}
        severity = data.get('severity')  # Use settings default if not provided
        
        result = scan_all_container_images(severity)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@vulnerabilities_bp.route('/vulnerabilities/results')
@login_required
def api_get_all_results():
    """Get all stored vulnerability scan results."""
    results = get_stored_vulnerabilities()
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
        severity_filter=data.get('severity_filter')
    )
    return jsonify(result)


@vulnerabilities_bp.route('/vulnerabilities/scan-container/<container_id>', methods=['POST'])
@login_required
def api_scan_container(container_id):
    """Scan a specific container's image for vulnerabilities."""
    data = request.get_json() or {}
    force = data.get('force', True)  # Force fresh scan by default
    
    result = scan_container_image(container_id, force=force)
    return jsonify(result)
