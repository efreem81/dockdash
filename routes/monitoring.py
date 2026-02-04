"""
Monitoring API Routes
Background monitoring and scheduler endpoints
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required

from services.scheduler_service import (
    start_monitoring, stop_monitoring, get_monitoring_status,
    update_thresholds
)

monitoring_bp = Blueprint('monitoring', __name__)


@monitoring_bp.route('/monitoring/status')
@login_required
def api_monitoring_status():
    """Get current monitoring status."""
    status = get_monitoring_status()
    return jsonify({'success': True, **status})


@monitoring_bp.route('/monitoring/start', methods=['POST'])
@login_required
def api_start_monitoring():
    """Start background monitoring."""
    result = start_monitoring(current_app._get_current_object())
    return jsonify(result)


@monitoring_bp.route('/monitoring/stop', methods=['POST'])
@login_required
def api_stop_monitoring():
    """Stop background monitoring."""
    result = stop_monitoring()
    return jsonify(result)


@monitoring_bp.route('/monitoring/thresholds', methods=['POST'])
@login_required
def api_update_thresholds():
    """Update monitoring thresholds."""
    data = request.get_json() or {}
    
    cpu = data.get('cpu_threshold')
    memory = data.get('memory_threshold')
    
    if cpu is not None:
        try:
            cpu = float(cpu)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid CPU threshold'}), 400
    
    if memory is not None:
        try:
            memory = float(memory)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid memory threshold'}), 400
    
    result = update_thresholds(cpu=cpu, memory=memory)
    return jsonify(result)
