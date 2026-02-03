"""
Vulnerability API Routes
Image security scanning endpoints
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.vulnerability_service import (
    is_trivy_available, scan_image, scan_multiple_images,
    get_vulnerability_report, clear_cache
)

vulnerabilities_bp = Blueprint('vulnerabilities', __name__)


@vulnerabilities_bp.route('/vulnerabilities/status')
@login_required
def api_scanner_status():
    """Check if vulnerability scanner is available."""
    available = is_trivy_available()
    return jsonify({
        'success': True,
        'scanner': 'trivy',
        'available': available,
        'message': 'Trivy scanner is ready' if available else 'Trivy not installed'
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
