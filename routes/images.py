"""
Image API Routes
Image management: list, pull, delete, prune, check updates
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from services.image_service import (
    get_image_details, check_image_update
)
from services.fleet_service import (
    get_endpoint, list_images as fleet_list_images, image_action,
    check_endpoint_updates,
)

images_bp = Blueprint('images', __name__)


@images_bp.route('/images')
@login_required
def api_list_images():
    """List all images."""
    try:
        images = fleet_list_images(get_endpoint())
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    if isinstance(images, dict) and 'error' in images:
        return jsonify({'success': False, 'error': images['error']}), 500
    return jsonify({'success': True, 'images': images})


@images_bp.route('/image/<path:image_id>')
@login_required
def api_image_detail(image_id):
    """Get detailed info for an image."""
    endpoint = get_endpoint()
    if endpoint.kind != 'local':
        images = fleet_list_images(endpoint)
        details = next((item for item in images if item.get('id') == image_id or item.get('short_id') == image_id), None)
    else:
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

    try:
        result = image_action(get_endpoint(), 'pull', {'image': image_ref})
    except Exception as exc:
        result = {'success': False, 'error': str(exc)}
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/image/<path:image_id>/delete', methods=['POST'])
@login_required
def api_delete_image(image_id):
    """Delete an image."""
    force = request.json.get('force', False) if request.is_json else False
    try:
        result = image_action(get_endpoint(), 'delete', {'force': force}, image_id=image_id)
    except Exception as exc:
        result = {'success': False, 'error': str(exc)}
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/images/prune', methods=['POST'])
@login_required
def api_prune_images():
    """Remove unused images."""
    data = request.get_json() or {}
    dangling_only = data.get('dangling_only', True)
    try:
        result = image_action(get_endpoint(), 'prune', {'dangling_only': dangling_only})
    except Exception as exc:
        result = {'success': False, 'error': str(exc)}
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/volumes/prune', methods=['POST'])
@login_required
def api_prune_volumes():
    """Remove unused volumes."""
    try:
        result = image_action(get_endpoint(), 'prune-volumes')
    except Exception as exc:
        result = {'success': False, 'error': str(exc)}
    status = 200 if result['success'] else 500
    return jsonify(result), status


@images_bp.route('/system/prune', methods=['POST'])
@login_required
def api_prune_all():
    """Prune containers, images, and volumes."""
    try:
        result = image_action(get_endpoint(), 'prune-system')
        return jsonify(result)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 403


@images_bp.route('/image/check-update', methods=['GET', 'POST'])
@login_required
def api_check_image_update():
    """Check if an image has an update available."""
    data = request.get_json(silent=True) or {}
    image = (request.args.get('image') or data.get('image') or '').strip()

    if not image:
        return jsonify({'success': False, 'error': 'Image parameter required'}), 400

    endpoint = get_endpoint()
    if endpoint.kind == 'agent':
        try:
            payload = check_endpoint_updates(endpoint, [image])
            result = payload.get('results', {}).get(image)
            if not result:
                raise RuntimeError('Agent returned no update result for the requested image')
            from services.update_service import save_update_result
            save_update_result(image, result, endpoint_id=endpoint.id)
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)}), 502
    else:
        result = check_image_update(image)
        from services.update_service import save_update_result
        save_update_result(image, result, endpoint_id=endpoint.id)
    result['success'] = result['error'] is None or result['has_update'] is not None
    return jsonify(result)


@images_bp.route('/images/check-updates', methods=['POST'])
@login_required
def api_check_images_updates():
    """Check multiple images for updates and persist results."""
    endpoint = get_endpoint()
    from services.update_service import check_and_save_update, save_update_result

    data = request.get_json() or {}
    images = data.get('images', [])

    if not images or not isinstance(images, list):
        return jsonify({'success': False, 'error': 'images array required'}), 400

    if len(images) > 50:
        return jsonify({'success': False, 'error': 'Maximum 50 images per request'}), 400

    unique_images = list(dict.fromkeys(images))
    if endpoint.kind == 'agent':
        try:
            payload = check_endpoint_updates(endpoint, unique_images)
            results = payload.get('results', {})
            for image_ref, result in results.items():
                save_update_result(image_ref, result, endpoint_id=endpoint.id)
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)}), 502
    else:
        results = {
            image_ref: check_and_save_update(image_ref, endpoint_id=endpoint.id)
            for image_ref in unique_images
        }

    return jsonify({'success': True, 'results': results})


@images_bp.route('/updates/status')
@login_required
def api_get_stored_updates():
    """Get all stored update check results."""
    from services.update_service import get_stored_updates, get_update_settings

    endpoint = get_endpoint()
    updates = get_stored_updates(endpoint_id=endpoint.id)
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
    endpoint = get_endpoint()
    from services.update_service import check_all_container_images, save_update_result

    if endpoint.kind == 'agent':
        try:
            result = check_endpoint_updates(endpoint)
            for image_ref, update_result in result.get('results', {}).items():
                save_update_result(image_ref, update_result, endpoint_id=endpoint.id)
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)}), 502
    else:
        result = check_all_container_images(endpoint_id=endpoint.id)
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

    endpoint = get_endpoint()
    clear_update_status(image_ref, endpoint_id=endpoint.id)
    return jsonify({'success': True, 'message': 'Update status cleared'})
