"""
Update Service - Image Update Checking and Persistence
Handles checking for image updates, storing results, and scheduled checks.
"""
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from services.docker_service import get_all_containers
from services.image_service import check_image_update

logger = logging.getLogger('update_checker')


def _log(level: int, message: str):
    """Log a message with the update checker prefix."""
    logger.log(level, f"[UPDATE] {message}")


# =============================================================================
# Settings Management
# =============================================================================

def get_update_settings() -> Dict[str, Any]:
    """Get current update check settings."""
    from models import UpdateSettings
    
    try:
        settings = UpdateSettings.get_settings()
        return {
            'enabled': settings.enabled,
            'schedule_type': settings.schedule_type,
            'schedule_hour': settings.schedule_hour,
            'schedule_minute': settings.schedule_minute,
            'schedule_day': settings.schedule_day,
            'last_check_started': settings.last_check_started.isoformat() if settings.last_check_started else None,
            'last_check_completed': settings.last_check_completed.isoformat() if settings.last_check_completed else None,
            'last_check_images_count': settings.last_check_images_count,
            'images_with_updates': settings.images_with_updates
        }
    except Exception as e:
        _log(logging.ERROR, f"Error getting settings: {e}")
        return {
            'enabled': False,
            'schedule_type': 'daily',
            'schedule_hour': 4,
            'schedule_minute': 0,
            'schedule_day': 0
        }


def update_update_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Update the update check settings."""
    from config import db
    from models import UpdateSettings
    
    try:
        settings = UpdateSettings.get_settings()
        
        if 'enabled' in data:
            settings.enabled = bool(data['enabled'])
        if 'schedule_type' in data:
            settings.schedule_type = data['schedule_type']
        if 'schedule_hour' in data:
            settings.schedule_hour = int(data['schedule_hour']) % 24
        if 'schedule_minute' in data:
            settings.schedule_minute = int(data['schedule_minute']) % 60
        if 'schedule_day' in data:
            settings.schedule_day = int(data['schedule_day']) % 7
        
        db.session.commit()
        _log(logging.INFO, f"Update settings saved: enabled={settings.enabled}, type={settings.schedule_type}")
        
        return {'success': True, 'message': 'Settings saved'}
    except Exception as e:
        _log(logging.ERROR, f"Error saving settings: {e}")
        return {'success': False, 'error': str(e)}


# =============================================================================
# Update Status Storage
# =============================================================================

def save_update_result(image_ref: str, result: Dict[str, Any]):
    """Save an update check result to the database."""
    from config import db
    from models import ImageUpdate
    
    try:
        update = ImageUpdate.query.filter_by(image_ref=image_ref).first()
        if not update:
            update = ImageUpdate(image_ref=image_ref)
            db.session.add(update)
        
        update.has_update = result.get('has_update', False) or False
        update.local_digest = result.get('local_digest')
        update.remote_digest = result.get('remote_digest')
        update.error = result.get('error')
        update.checked_at = datetime.utcnow()
        
        db.session.commit()
        return True
    except Exception as e:
        _log(logging.ERROR, f"Error saving update result for {image_ref}: {e}")
        return False


def get_stored_updates() -> Dict[str, Dict]:
    """Get all stored update check results."""
    from models import ImageUpdate
    
    try:
        updates = ImageUpdate.query.all()
        return {u.image_ref: u.to_dict() for u in updates}
    except Exception:
        return {}


def get_image_update_status(image_ref: str) -> Optional[Dict]:
    """Get stored update status for a specific image."""
    from models import ImageUpdate
    
    try:
        update = ImageUpdate.query.filter_by(image_ref=image_ref).first()
        return update.to_dict() if update else None
    except Exception:
        return None


def clear_update_status(image_ref: str = None):
    """Clear stored update status for an image or all images.
    
    When clearing a specific image, we set has_update=False rather than deleting,
    so we preserve the check history. When clearing all, we delete everything.
    """
    from config import db
    from models import ImageUpdate
    from datetime import datetime
    
    try:
        if image_ref:
            # For a specific image, just mark it as no longer having an update
            update = ImageUpdate.query.filter_by(image_ref=image_ref).first()
            if update:
                update.has_update = False
                update.checked_at = datetime.utcnow()
                db.session.commit()
        else:
            ImageUpdate.query.delete()
            db.session.commit()
        return True
    except Exception as e:
        _log(logging.ERROR, f"Error clearing update status: {e}")
        return False


# =============================================================================
# Update Checking
# =============================================================================

def check_and_save_update(image_ref: str) -> Dict[str, Any]:
    """Check for updates on an image and save the result."""
    result = check_image_update(image_ref)
    save_update_result(image_ref, result)
    return result


def check_all_container_images() -> Dict[str, Any]:
    """Check all container images for updates and store results."""
    from config import db
    from models import UpdateSettings
    
    _log(logging.INFO, "=== Starting full update check ===")
    
    # Update settings to mark check started
    try:
        settings = UpdateSettings.get_settings()
        settings.last_check_started = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        _log(logging.ERROR, f"Could not update check start time: {e}")
    
    # Get all unique images
    containers = get_all_containers(show_all=True)
    images = list(set(c.get('image') for c in containers if c.get('image') and c.get('image') != 'unknown'))
    
    _log(logging.INFO, f"Checking {len(images)} unique images for updates")
    
    results = {}
    updates_found = 0
    errors = 0
    
    for i, image in enumerate(images):
        _log(logging.DEBUG, f"Checking [{i+1}/{len(images)}]: {image}")
        try:
            result = check_and_save_update(image)
            results[image] = result
            if result.get('has_update'):
                updates_found += 1
                _log(logging.INFO, f"  ⬆️ Update available for {image}")
            elif result.get('error'):
                errors += 1
                _log(logging.WARNING, f"  ⚠️ Error checking {image}: {result['error']}")
        except Exception as e:
            errors += 1
            _log(logging.ERROR, f"  ❌ Failed to check {image}: {e}")
            results[image] = {'error': str(e), 'has_update': None}
    
    # Update settings with completion info
    try:
        settings = UpdateSettings.get_settings()
        settings.last_check_completed = datetime.utcnow()
        settings.last_check_images_count = len(images)
        settings.images_with_updates = updates_found
        db.session.commit()
    except Exception as e:
        _log(logging.ERROR, f"Could not update check completion: {e}")
    
    _log(logging.INFO, f"=== Update check complete: {updates_found} updates, {errors} errors ===")
    
    return {
        'success': True,
        'images_checked': len(images),
        'updates_found': updates_found,
        'errors': errors,
        'results': results
    }


# =============================================================================
# Scheduled Check (called by background scheduler)
# =============================================================================

def should_run_scheduled_check() -> bool:
    """Check if a scheduled update check should run now."""
    from models import UpdateSettings
    
    try:
        settings = UpdateSettings.get_settings()
        if not settings.enabled:
            return False
        
        now = datetime.now()
        
        # Check if we're in the right time window (within 5 minutes)
        if now.hour != settings.schedule_hour:
            return False
        if abs(now.minute - settings.schedule_minute) > 5:
            return False
        
        # For weekly, check day of week
        if settings.schedule_type == 'weekly':
            if now.weekday() != settings.schedule_day:
                return False
        
        # Check if we already ran recently (within last hour)
        if settings.last_check_completed:
            delta = now - settings.last_check_completed
            if delta.total_seconds() < 3600:
                return False
        
        return True
    except Exception:
        return False


def run_scheduled_check_if_due():
    """Run a scheduled check if it's time."""
    if should_run_scheduled_check():
        _log(logging.INFO, "Running scheduled update check")
        check_all_container_images()
