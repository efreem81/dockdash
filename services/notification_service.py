"""
Notification Service - Webhook and Alert Management
Supports Discord, Slack, Telegram, and generic webhooks
"""
import requests
from datetime import datetime


def send_webhook(webhook_config, title, message, color='info', fields=None):
    """Send notification to a webhook based on its type."""
    webhook_type = webhook_config.webhook_type
    webhook_url = webhook_config.webhook_url
    
    if not webhook_config.enabled:
        return {'success': False, 'error': 'Webhook is disabled'}
    
    try:
        if webhook_type == 'discord':
            return _send_discord(webhook_url, title, message, color, fields)
        elif webhook_type == 'slack':
            return _send_slack(webhook_url, title, message, color, fields)
        elif webhook_type == 'telegram':
            return _send_telegram(webhook_url, title, message, fields)
        else:
            return _send_generic(webhook_url, title, message, color, fields)
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _get_color_hex(color):
    """Convert color name to hex for Discord."""
    colors = {
        'info': 0x3B82F6,
        'success': 0x10B981,
        'warning': 0xF59E0B,
        'danger': 0xEF4444,
        'error': 0xEF4444,
    }
    return colors.get(color, 0x3B82F6)


def _send_discord(webhook_url, title, message, color='info', fields=None):
    """Send Discord webhook notification."""
    embed = {
        'title': f'🐳 {title}',
        'description': message,
        'color': _get_color_hex(color),
        'timestamp': datetime.utcnow().isoformat(),
        'footer': {'text': 'DockDash'}
    }
    
    if fields:
        embed['fields'] = [{'name': k, 'value': str(v), 'inline': True} for k, v in fields.items()]
    
    payload = {'embeds': [embed]}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    
    return {
        'success': resp.status_code in (200, 204),
        'status_code': resp.status_code
    }


def _send_slack(webhook_url, title, message, color='info', fields=None):
    """Send Slack webhook notification."""
    color_map = {
        'info': '#3B82F6',
        'success': '#10B981',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'error': '#EF4444',
    }
    
    attachment = {
        'color': color_map.get(color, '#3B82F6'),
        'title': f'🐳 {title}',
        'text': message,
        'footer': 'DockDash',
        'ts': int(datetime.utcnow().timestamp())
    }
    
    if fields:
        attachment['fields'] = [{'title': k, 'value': str(v), 'short': True} for k, v in fields.items()]
    
    payload = {'attachments': [attachment]}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    
    return {
        'success': resp.status_code == 200,
        'status_code': resp.status_code
    }


def _send_telegram(webhook_url, title, message, fields=None):
    """Send Telegram notification. URL format: https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>"""
    text = f"🐳 *{title}*\n\n{message}"
    
    if fields:
        text += "\n\n"
        for k, v in fields.items():
            text += f"• *{k}:* {v}\n"
    
    # Parse bot token and chat_id from URL or use as-is
    if 'chat_id=' in webhook_url:
        # URL already has chat_id parameter
        payload = {'text': text, 'parse_mode': 'Markdown'}
        resp = requests.post(webhook_url, json=payload, timeout=10)
    else:
        payload = {'text': text, 'parse_mode': 'Markdown'}
        resp = requests.post(webhook_url, json=payload, timeout=10)
    
    return {
        'success': resp.status_code == 200,
        'status_code': resp.status_code
    }


def _send_generic(webhook_url, title, message, color='info', fields=None):
    """Send generic webhook notification."""
    payload = {
        'title': title,
        'message': message,
        'severity': color,
        'timestamp': datetime.utcnow().isoformat(),
        'source': 'DockDash',
        'fields': fields or {}
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    
    return {
        'success': resp.status_code in (200, 201, 202, 204),
        'status_code': resp.status_code
    }


def send_container_alert(webhook_configs, container_name, event_type, details=None):
    """Send container state change alert to all configured webhooks."""
    titles = {
        'stopped': 'Container Stopped',
        'started': 'Container Started',
        'unhealthy': 'Container Unhealthy',
        'healthy': 'Container Healthy',
        'high_cpu': 'High CPU Usage',
        'high_memory': 'High Memory Usage',
    }
    
    colors = {
        'stopped': 'danger',
        'started': 'success',
        'unhealthy': 'warning',
        'healthy': 'success',
        'high_cpu': 'warning',
        'high_memory': 'warning',
    }
    
    title = titles.get(event_type, 'Container Alert')
    color = colors.get(event_type, 'info')
    message = f"Container **{container_name}** {event_type}"
    
    results = []
    for config in webhook_configs:
        # Check if this webhook should receive this alert type
        should_send = False
        if event_type == 'stopped' and config.alert_container_stop:
            should_send = True
        elif event_type == 'started' and config.alert_container_start:
            should_send = True
        elif event_type in ('unhealthy', 'healthy') and config.alert_health_unhealthy:
            should_send = True
        elif event_type in ('high_cpu', 'high_memory'):
            should_send = True  # Always send resource alerts if configured
        
        if should_send:
            result = send_webhook(config, title, message, color, details)
            result['webhook_name'] = config.name
            results.append(result)
    
    return results


def test_webhook(webhook_type, webhook_url):
    """Send a test notification to verify webhook configuration."""
    class MockConfig:
        def __init__(self):
            self.webhook_type = webhook_type
            self.webhook_url = webhook_url
            self.enabled = True
    
    return send_webhook(
        MockConfig(),
        'Test Notification',
        'This is a test notification from DockDash.',
        'info',
        {'Status': 'Connected', 'Time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
    )
