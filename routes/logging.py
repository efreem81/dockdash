"""Logging settings API routes."""

import logging
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required

from services.logging_service import configure_app_logging, set_db_log_level, normalize_level

logging_bp = Blueprint('logging', __name__)
logger = logging.getLogger(__name__)


@logging_bp.route('/logging/settings', methods=['GET'])
@login_required
def api_get_logging_settings():
    from models import AppSettings

    settings = AppSettings.get_settings()
    return jsonify({'success': True, 'settings': {'log_level': settings.log_level or 'INFO'}})


@logging_bp.route('/logging/settings', methods=['POST'])
@login_required
def api_update_logging_settings():
    data = request.get_json() or {}
    requested = normalize_level(data.get('log_level'))

    applied = set_db_log_level(requested)
    configure_app_logging(current_app._get_current_object(), level=applied)

    logger.info('Updated app log level to %s', applied)
    return jsonify({'success': True, 'settings': {'log_level': applied}})
