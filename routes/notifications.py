"""
Notification API Routes
Webhook configuration and testing
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from models import WebhookConfig
from config import db
from services.notification_service import test_webhook, send_container_alert

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/webhooks')
@login_required
def list_webhooks():
    """List all webhook configurations."""
    webhooks = WebhookConfig.query.all()
    return jsonify({
        'success': True,
        'webhooks': [{
            'id': w.id,
            'name': w.name,
            'webhook_type': w.webhook_type,
            'enabled': w.enabled,
            'alert_container_stop': w.alert_container_stop,
            'alert_container_start': w.alert_container_start,
            'alert_health_unhealthy': w.alert_health_unhealthy,
            'alert_cpu_threshold': w.alert_cpu_threshold,
            'alert_memory_threshold': w.alert_memory_threshold,
        } for w in webhooks]
    })


@notifications_bp.route('/webhook', methods=['POST'])
@login_required
def create_webhook():
    """Create a new webhook configuration."""
    data = request.get_json() or {}
    
    required = ['name', 'webhook_type', 'webhook_url']
    if not all(k in data for k in required):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    webhook = WebhookConfig(
        name=data['name'],
        webhook_type=data['webhook_type'],
        webhook_url=data['webhook_url'],
        enabled=data.get('enabled', True),
        alert_container_stop=data.get('alert_container_stop', True),
        alert_container_start=data.get('alert_container_start', False),
        alert_health_unhealthy=data.get('alert_health_unhealthy', True),
        alert_cpu_threshold=data.get('alert_cpu_threshold', 90),
        alert_memory_threshold=data.get('alert_memory_threshold', 90),
    )
    
    db.session.add(webhook)
    db.session.commit()
    
    return jsonify({'success': True, 'id': webhook.id, 'message': 'Webhook created'})


@notifications_bp.route('/webhook/<int:webhook_id>', methods=['PUT'])
@login_required
def update_webhook(webhook_id):
    """Update a webhook configuration."""
    webhook = WebhookConfig.query.get_or_404(webhook_id)
    data = request.get_json() or {}
    
    if 'name' in data:
        webhook.name = data['name']
    if 'webhook_type' in data:
        webhook.webhook_type = data['webhook_type']
    if 'webhook_url' in data:
        webhook.webhook_url = data['webhook_url']
    if 'enabled' in data:
        webhook.enabled = data['enabled']
    if 'alert_container_stop' in data:
        webhook.alert_container_stop = data['alert_container_stop']
    if 'alert_container_start' in data:
        webhook.alert_container_start = data['alert_container_start']
    if 'alert_health_unhealthy' in data:
        webhook.alert_health_unhealthy = data['alert_health_unhealthy']
    if 'alert_cpu_threshold' in data:
        webhook.alert_cpu_threshold = data['alert_cpu_threshold']
    if 'alert_memory_threshold' in data:
        webhook.alert_memory_threshold = data['alert_memory_threshold']
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Webhook updated'})


@notifications_bp.route('/webhook/<int:webhook_id>', methods=['DELETE'])
@login_required
def delete_webhook(webhook_id):
    """Delete a webhook configuration."""
    webhook = WebhookConfig.query.get_or_404(webhook_id)
    db.session.delete(webhook)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Webhook deleted'})


@notifications_bp.route('/webhook/<int:webhook_id>/test', methods=['POST'])
@login_required
def test_webhook_endpoint(webhook_id):
    """Send a test notification to a webhook."""
    webhook = WebhookConfig.query.get_or_404(webhook_id)
    result = test_webhook(webhook.webhook_type, webhook.webhook_url)
    
    return jsonify({
        'success': result.get('success', False),
        'status_code': result.get('status_code'),
        'error': result.get('error')
    })


@notifications_bp.route('/webhook/test', methods=['POST'])
@login_required
def test_webhook_url():
    """Test a webhook URL without saving it."""
    data = request.get_json() or {}
    
    webhook_type = data.get('webhook_type')
    webhook_url = data.get('webhook_url')
    
    if not webhook_type or not webhook_url:
        return jsonify({'success': False, 'error': 'webhook_type and webhook_url required'}), 400
    
    result = test_webhook(webhook_type, webhook_url)
    
    return jsonify({
        'success': result.get('success', False),
        'status_code': result.get('status_code'),
        'error': result.get('error')
    })
