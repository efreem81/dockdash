"""
Image API Routes
Image management: list, pull, delete, prune, check updates
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.image_service import (
    list_images, get_image_details, pull_image, delete_image,
    prune_images, prune_volumes, prune_all,
    check_image_update
)

images_bp = Blueprint('images', __name__)


@images_bp.route('/images')
@login_required
def api_list_images():
    """List all images."""
    images = list_images()
    if isinstance(images, dict) and 'error' in images:
        return jsonify({'success': False, 'error': images['error']}), 500
    return jsonify({'success': True, 'images': images})


@images_bp.route('/image/<path:image_id>')
@login_required
def api_image_detail(image_id):
    """Get detailed info for an image."""
    details = get_image_details(image_id)
    if not details:
        return jsonify({'success': False, 'error': 'Image not found'}), 404
    if 'error' in details:
        return jsonify({'success': False, 'error': details['error']}), 500
    return jsonify({'success': True, 'image': details})


@images_bp.route('/image/pull', methods=['POST'])
@login_required
def api_pull_image():
    """Pull an image from registry."""
    data = request.get_json() or {}
    image_ref = data.get('image')
    
    if not image_ref:
        return jsonify({'success': False, 'error': 'Image reference required'}), 400
    
    result = pull_image(image_ref)
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/image/<path:image_id>/delete', methods=['POST'])
@login_required
def api_delete_image(image_id):
    """Delete an image."""
    force = request.json.get('force', False) if request.is_json else False
    result = delete_image(image_id, force=force)
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/images/prune', methods=['POST'])
@login_required
def api_prune_images():
    """Remove unused images."""
    data = request.get_json() or {}
    dangling_only = data.get('dangling_only', True)
    result = prune_images(dangling_only=dangling_only)
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/volumes/prune', methods=['POST'])
@login_required
def api_prune_volumes():
    """Remove unused volumes."""
    result = prune_volumes()
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/system/prune', methods=['POST'])
@login_required
def api_prune_all():
    """Prune containers, images, and volumes."""
    result = prune_all()
    return jsonify(result)


@images_bp.route('/image/check-update')
@login_required
def api_check_image_update():
    """Check if an image has an update available."""
    image = (request.args.get('image') or '').strip()
    
    if not image:
        return jsonify({'success': False, 'error': 'Image parameter required'}), 400
    
    result = check_image_update(image)
    result['success'] = result['error'] is None or result['has_update'] is not None
    return jsonify(result)


@images_bp.route('/images/check-updates', methods=['POST'])
@login_required
def api_check_images_updates():
    """Check multiple images for updates and persist results."""
    from services.update_service import check_and_save_update
    
    data = request.get_json() or {}
    images = data.get('images', [])
    
    if not images or not isinstance(images, list):
        return jsonify({'success': False, 'error': 'images array required'}), 400
    
    if len(images) > 50:
        return jsonify({'success': False, 'error': 'Maximum 50 images per request'}), 400
    
    unique_images = list(set(images))
    results = {img: check_and_save_update(img) for img in unique_images}
    
    return jsonify({'success': True, 'results': results})


@images_bp.route('/updates/status')
@login_required
def api_get_stored_updates():
    """Get all stored update check results."""
    from services.update_service import get_stored_updates, get_update_settings
    
    updates = get_stored_updates()
    settings = get_update_settings()
    
    return jsonify({
        'success': True,
        'updates': updates,
        'settings': settings
    })


@images_bp.route('/updates/check-all', methods=['POST'])
@login_required
def api_check_all_updates():
    """Check all container images for updates."""
    from services.update_service import check_all_container_images
    
    result = check_all_container_images()
    return jsonify(result)


@images_bp.route('/updates/settings', methods=['GET', 'POST'])
@login_required
def api_update_settings():
    """Get or update the update check settings."""
    from services.update_service import get_update_settings, update_update_settings
    
    if request.method == 'GET':
        settings = get_update_settings()
        return jsonify({'success': True, 'settings': settings})
    
    data = request.get_json() or {}
    result = update_update_settings(data)
    return jsonify(result)


@images_bp.route('/updates/clear', methods=['POST'])
@login_required
def api_clear_updates():
    """Clear stored update statuses."""
    from services.update_service import clear_update_status
    
    data = request.get_json() or {}
    image_ref = data.get('image')
    
    clear_update_status(image_ref)
    return jsonify({'success': True, 'message': 'Update status cleared'})

