"""
Scheduler Service - Background Monitoring and Alerting
Uses APScheduler to poll container stats and trigger alerts
"""
import os
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable

# Global scheduler state
_scheduler = None
_is_running = False
_jobs: Dict[str, dict] = {}
_last_check: Dict[str, dict] = {}

# Thresholds (can be overridden via environment)
CPU_THRESHOLD = float(os.environ.get('ALERT_CPU_THRESHOLD', 80))
MEMORY_THRESHOLD = float(os.environ.get('ALERT_MEMORY_THRESHOLD', 85))
CHECK_INTERVAL = int(os.environ.get('MONITOR_INTERVAL', 60))  # seconds


class SimpleScheduler:
    """Simple background scheduler using threading."""
    
    def __init__(self):
        self.jobs: Dict[str, dict] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def add_job(self, job_id: str, func: Callable, interval_seconds: int, **kwargs):
        """Add a recurring job."""
        self.jobs[job_id] = {
            'func': func,
            'interval': interval_seconds,
            'kwargs': kwargs,
            'last_run': 0
        }
    
    def remove_job(self, job_id: str):
        """Remove a job."""
        self.jobs.pop(job_id, None)
    
    def start(self):
        """Start the scheduler in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
    
    def _run(self):
        """Main scheduler loop."""
        while not self._stop_event.is_set():
            now = time.time()
            
            for job_id, job in list(self.jobs.items()):
                if (now - job['last_run']) >= job['interval']:
                    try:
                        job['func'](**job['kwargs'])
                        job['last_run'] = now
                    except Exception as e:
                        print(f"Scheduler job {job_id} failed: {e}")
            
            # Sleep in small increments to allow quick shutdown
            for _ in range(10):
                if self._stop_event.is_set():
                    break
                time.sleep(1)


def get_scheduler() -> SimpleScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SimpleScheduler()
    return _scheduler


def _run_with_app_context(app, job_func: Callable, **kwargs):
    """Run a scheduler job inside a Flask application context.

    Background threads don't automatically have Flask application context,
    so any DB access (models.query, db.session) will fail without this.
    """
    if app is None:
        job_func(**kwargs)
        return

    with app.app_context():
        job_func(**kwargs)


def start_monitoring(app=None):
    """Start the background monitoring service."""
    global _is_running
    
    if _is_running:
        return {'success': True, 'message': 'Monitoring already running'}
    
    if app is None:
        try:
            from flask import current_app
            app = current_app._get_current_object()
        except Exception:
            app = None

    scheduler = get_scheduler()
    
    # Add container stats monitoring job
    scheduler.add_job(
        'container_monitor',
        _run_with_app_context,
        interval_seconds=CHECK_INTERVAL,
        app=app,
        job_func=check_container_resources
    )
    
    # Add container state monitoring job
    scheduler.add_job(
        'state_monitor',
        _run_with_app_context,
        interval_seconds=30,
        app=app,
        job_func=check_container_states
    )
    
    # Add scheduled scan check (checks every minute if it's time to run)
    scheduler.add_job(
        'scheduled_scans',
        _run_with_app_context,
        interval_seconds=60,
        app=app,
        job_func=run_scheduled_tasks
    )
    
    scheduler.start()
    _is_running = True
    
    return {'success': True, 'message': 'Monitoring started'}


def run_scheduled_tasks():
    """Run scheduled vulnerability scans and update checks if due."""
    try:
        from services.vulnerability_service import run_scheduled_scan_if_due
        run_scheduled_scan_if_due()
    except Exception as e:
        print(f"Scheduled scan check failed: {e}")
    
    try:
        from services.update_service import run_scheduled_check_if_due
        run_scheduled_check_if_due()
    except Exception as e:
        print(f"Scheduled update check failed: {e}")


def stop_monitoring():
    """Stop the background monitoring service."""
    global _is_running, _scheduler
    
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
    
    _is_running = False
    return {'success': True, 'message': 'Monitoring stopped'}


def get_monitoring_status():
    """Get current monitoring status."""
    return {
        'running': _is_running,
        'check_interval': CHECK_INTERVAL,
        'cpu_threshold': CPU_THRESHOLD,
        'memory_threshold': MEMORY_THRESHOLD,
        'last_checks': _last_check
    }


def check_container_resources():
    """Check all running containers for resource threshold violations."""
    from services.docker_service import get_docker_client, get_container_stats
    from services.notification_service import send_container_alert
    from models import WebhookConfig
    
    client = get_docker_client()
    if not client:
        return
    
    try:
        containers = client.containers.list()
        webhooks = WebhookConfig.query.filter_by(enabled=True).all()
        
        for container in containers:
            try:
                stats = get_container_stats(container.short_id)
                if not stats or 'error' in stats:
                    continue
                
                container_name = container.name
                alerts_sent = []
                
                # Check CPU threshold
                cpu_percent = stats.get('cpu_percent', 0)
                if cpu_percent > CPU_THRESHOLD:
                    alert_key = f"cpu:{container.id}"
                    if not _should_suppress_alert(alert_key):
                        send_container_alert(
                            webhooks, container_name, 'high_cpu',
                            {'CPU Usage': f'{cpu_percent:.1f}%', 'Threshold': f'{CPU_THRESHOLD}%'}
                        )
                        _mark_alert_sent(alert_key)
                        alerts_sent.append('high_cpu')
                
                # Check memory threshold
                mem_percent = stats.get('memory_percent', 0)
                if mem_percent > MEMORY_THRESHOLD:
                    alert_key = f"mem:{container.id}"
                    if not _should_suppress_alert(alert_key):
                        send_container_alert(
                            webhooks, container_name, 'high_memory',
                            {'Memory Usage': f'{mem_percent:.1f}%', 'Threshold': f'{MEMORY_THRESHOLD}%'}
                        )
                        _mark_alert_sent(alert_key)
                        alerts_sent.append('high_memory')
                
                _last_check[container.short_id] = {
                    'name': container_name,
                    'cpu_percent': cpu_percent,
                    'memory_percent': mem_percent,
                    'checked_at': datetime.now().isoformat(),
                    'alerts_sent': alerts_sent
                }
                
            except Exception as e:
                print(f"Error checking container {container.name}: {e}")
                
    except Exception as e:
        print(f"Error in resource monitoring: {e}")


def check_container_states():
    """Check for container state changes (stopped unexpectedly)."""
    from services.docker_service import get_docker_client
    from services.notification_service import send_container_alert
    from models import WebhookConfig
    
    global _last_check
    
    client = get_docker_client()
    if not client:
        return
    
    try:
        # Get all containers including stopped
        containers = client.containers.list(all=True)
        webhooks = WebhookConfig.query.filter_by(enabled=True).all()
        
        current_states = {}
        for container in containers:
            current_states[container.id] = {
                'name': container.name,
                'status': container.status,
                'health': container.attrs.get('State', {}).get('Health', {}).get('Status')
            }
        
        # Check for state changes
        previous_states = _last_check.get('_container_states', {})
        
        for container_id, current in current_states.items():
            previous = previous_states.get(container_id)
            
            if previous:
                # Check if container stopped
                if previous['status'] == 'running' and current['status'] != 'running':
                    send_container_alert(
                        webhooks, current['name'], 'stopped',
                        {'Previous Status': previous['status'], 'Current Status': current['status']}
                    )
                
                # Check if container started
                elif previous['status'] != 'running' and current['status'] == 'running':
                    send_container_alert(
                        webhooks, current['name'], 'started',
                        {'Previous Status': previous['status'], 'Current Status': current['status']}
                    )
                
                # Check health status changes
                if previous.get('health') == 'healthy' and current.get('health') == 'unhealthy':
                    send_container_alert(
                        webhooks, current['name'], 'unhealthy',
                        {'Health Status': current['health']}
                    )
        
        _last_check['_container_states'] = current_states
        _last_check['_states_checked_at'] = datetime.now().isoformat()
        
    except Exception as e:
        print(f"Error in state monitoring: {e}")


# Alert suppression to avoid spam
_alert_cooldown: Dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 300  # 5 minutes


def _should_suppress_alert(alert_key: str) -> bool:
    """Check if an alert should be suppressed due to cooldown."""
    last_sent = _alert_cooldown.get(alert_key, 0)
    return (time.time() - last_sent) < ALERT_COOLDOWN_SECONDS


def _mark_alert_sent(alert_key: str):
    """Mark an alert as sent for cooldown tracking."""
    _alert_cooldown[alert_key] = time.time()


def update_thresholds(cpu: Optional[float] = None, memory: Optional[float] = None):
    """Update monitoring thresholds."""
    global CPU_THRESHOLD, MEMORY_THRESHOLD
    
    if cpu is not None:
        CPU_THRESHOLD = max(0, min(100, cpu))
    if memory is not None:
        MEMORY_THRESHOLD = max(0, min(100, memory))
    
    return {
        'success': True,
        'cpu_threshold': CPU_THRESHOLD,
        'memory_threshold': MEMORY_THRESHOLD
    }
