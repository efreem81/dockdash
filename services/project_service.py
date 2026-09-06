"""Compose project discovery, adoption, deployment jobs, and revisions."""
from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime

from config import db
from models import ComposeProject, DeploymentRevision, OperationJob
from services.agent_client import AgentClient


ACTION_OPTION_KEYS = {
    'validate': set(),
    'start': {'services'},
    'stop': {'services'},
    'restart': {'services'},
    'pull': {'services'},
    'up': {'services'},
    'recreate': {'services'},
    'logs': {'services', 'tail'},
    'scale': {'scales'},
    'down': set(),
}


def _client(endpoint):
    if endpoint.kind != 'agent':
        raise RuntimeError('Compose orchestration requires the DockDash agent, including on the controller host')
    return AgentClient(endpoint)


def discover_projects(endpoint):
    return _client(endpoint).get('/v1/projects', timeout=90).get('projects', [])


def adopt_project(endpoint, discovered):
    project = ComposeProject.query.filter_by(endpoint_id=endpoint.id, name=discovered['name']).first()
    if not project:
        project = ComposeProject(endpoint_id=endpoint.id, name=discovered['name'])
        db.session.add(project)
    project.working_dir = discovered['working_dir']
    project.config_files = discovered.get('config_files') or []
    project.config_digest = discovered.get('config_digest')
    if not project.source_type:
        project.source_type = 'adopted'
    db.session.commit()
    return project


def sync_projects(endpoint):
    found = discover_projects(endpoint)
    projects = [adopt_project(endpoint, item) for item in found]
    seen = {item['name'] for item in found}
    stale = ComposeProject.query.filter_by(endpoint_id=endpoint.id, source_type='adopted').all()
    for project in stale:
        if project.name not in seen and not project.revisions and not project.operations:
            db.session.delete(project)
    db.session.commit()
    return projects


def project_state(project):
    return _client(project.endpoint).post('/v1/projects/state', json=_project_payload(project)).get('state', {})


def _project_payload(project):
    return {
        'name': project.name,
        'working_dir': project.working_dir,
        'config_files': project.config_files,
        'required_mounts': project.required_mounts,
        'healthcheck_url': project.healthcheck_url,
        'healthcheck_timeout': project.healthcheck_timeout,
        'healthcheck_statuses': project.healthcheck_statuses,
        'source_type': project.source_type,
    }


def _new_revision(project, state, compose_content=None, source_revision=None):
    last = DeploymentRevision.query.filter_by(project_id=project.id).order_by(DeploymentRevision.revision.desc()).first()
    revision = DeploymentRevision(
        project_id=project.id,
        revision=(last.revision + 1) if last else 1,
        source_revision=source_revision,
        config_digest=state.get('config_digest') or project.config_digest,
        compose_content=compose_content,
    )
    revision.image_state = state.get('images') or {}
    db.session.add(revision)
    return revision


def sanitize_action_options(action, options=None):
    """Allow only non-authoritative action options into an agent request."""
    if action not in ACTION_OPTION_KEYS:
        raise ValueError(f'Unsupported project action: {action}')
    options = options or {}
    if not isinstance(options, dict):
        raise ValueError('Project action options must be an object')
    unexpected = sorted(set(options) - ACTION_OPTION_KEYS[action])
    if unexpected:
        raise ValueError('Unsupported project action options: ' + ', '.join(unexpected))
    sanitized = {}
    if 'services' in options:
        services = options['services']
        if not isinstance(services, list) or not all(isinstance(item, str) for item in services):
            raise ValueError('services must be a list of service names')
        sanitized['services'] = services
    if 'tail' in options:
        sanitized['tail'] = max(1, min(2000, int(options['tail'])))
    if 'scales' in options:
        scales = options['scales']
        if not isinstance(scales, dict):
            raise ValueError('scales must be an object')
        sanitized['scales'] = scales
    return sanitized


def queue_project_action(app, project, action, requested_by, options=None):
    del app  # Jobs are executed by the persistent dockdash-worker service.
    options = sanitize_action_options(action, options)
    job = OperationJob(
        endpoint_id=project.endpoint_id,
        project_id=project.id,
        action=action,
        status='queued',
        requested_by=requested_by,
        request_json=json.dumps(options),
    )
    db.session.add(job)
    db.session.commit()
    return job


def recover_interrupted_jobs():
    """Return jobs abandoned by a prior worker process to the durable queue."""
    jobs = OperationJob.query.filter_by(status='running').all()
    for job in jobs:
        job.status = 'queued'
        job.stage = 'recovered'
        job.error = None
        job.started_at = None
    db.session.commit()
    return len(jobs)


def claim_next_job():
    """Atomically claim the oldest job; one worker serializes fleet mutations."""
    candidate = OperationJob.query.filter_by(status='queued').order_by(OperationJob.id).first()
    if candidate is None:
        return None
    changed = OperationJob.query.filter_by(id=candidate.id, status='queued').update({
        OperationJob.status: 'running',
        OperationJob.stage: 'capture',
        OperationJob.started_at: datetime.utcnow(),
    }, synchronize_session=False)
    db.session.commit()
    return candidate.id if changed == 1 else None


def run_claimed_job(job_id):
    """Execute a job that has already been atomically claimed by the worker."""
    job = db.session.get(OperationJob, job_id)
    if job is None or job.status != 'running':
        return False
    try:
        project = db.session.get(ComposeProject, job.project_id)
        options = json.loads(job.request_json or '{}')
        if not isinstance(options, dict):
            raise ValueError('Stored project action options must be an object')
        options = sanitize_action_options(job.action, options)
        if project is None:
            raise RuntimeError('Compose project no longer exists')
        if project.endpoint_id != job.endpoint_id:
            raise RuntimeError('Compose project endpoint does not match queued job endpoint')
        before = project_state(project)
        job.before_state_json = json.dumps(before)
        _new_revision(project, before)
        db.session.commit()

        job.stage = 'execute'
        db.session.commit()
        payload = _project_payload(project)
        payload.update(options)
        payload['action'] = job.action
        result = _client(project.endpoint).post('/v1/projects/action', json=payload, timeout=1800)

        job.stage = 'verify'
        db.session.commit()
        after = result.get('state') or project_state(project)
        job.after_state_json = json.dumps(after)
        job.output = (result.get('output') or '')[-50000:]
        job.status = 'succeeded'
        job.stage = 'complete'
        job.completed_at = datetime.utcnow()
        project.config_digest = after.get('config_digest') or project.config_digest
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        job = db.session.get(OperationJob, job_id)
        if job is not None:
            job.status = 'failed'
            job.stage = 'failed'
            job.error = str(exc)[:10000]
            job.completed_at = datetime.utcnow()
            db.session.commit()
        return False


def run_worker(app, once=False, poll_interval=1.0):
    """Run the persistent, serialized Compose operation worker."""
    lock_path = os.environ.get(
        'DOCKDASH_WORKER_LOCK',
        os.path.join(app.root_path, 'data', 'dockdash-worker.lock'),
    )
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'w', encoding='utf-8') as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another DockDash project worker is already active') from exc

        with app.app_context():
            recover_interrupted_jobs()
        while True:
            with app.app_context():
                job_id = claim_next_job()
                if job_id is not None:
                    try:
                        run_claimed_job(job_id)
                    except Exception as exc:
                        db.session.rollback()
                        job = db.session.get(OperationJob, job_id)
                        if job is not None:
                            job.status = 'failed'
                            job.stage = 'failed'
                            job.error = f'Unexpected worker error: {exc}'[:10000]
                            job.completed_at = datetime.utcnow()
                            db.session.commit()
            if once:
                return job_id is not None
            if job_id is None:
                time.sleep(poll_interval)


def create_managed_project(
    endpoint, name, compose_content, healthcheck_url=None, required_mounts=None,
    healthcheck_statuses=None,
):
    payload = {
        'name': name,
        'compose_content': compose_content,
    }
    result = _client(endpoint).post('/v1/projects/managed', json=payload, timeout=90)
    discovered = result['project']
    project = adopt_project(endpoint, discovered)
    project.source_type = 'managed'
    project.compose_path = discovered['config_files'][0] if discovered.get('config_files') else None
    project.healthcheck_url = healthcheck_url or None
    project.required_mounts = required_mounts or []
    project.healthcheck_statuses = healthcheck_statuses or []
    state = result.get('state') or {}
    # Compose can reference secrets. Retain only its digest and image state in
    # the controller database; the owning host remains the source of truth.
    _new_revision(project, state)
    db.session.commit()
    return project


def create_git_project(endpoint, name, repo_url, repo_ref='main', compose_path='compose.yaml'):
    result = _client(endpoint).post('/v1/projects/git', json={
        'name': name,
        'repo_url': repo_url,
        'repo_ref': repo_ref,
        'compose_path': compose_path,
    }, timeout=300)
    project = adopt_project(endpoint, result['project'])
    project.source_type = 'git'
    project.repo_url = repo_url
    project.repo_ref = repo_ref
    project.compose_path = compose_path
    _new_revision(project, result.get('state') or {}, source_revision=result.get('source_revision'))
    db.session.commit()
    return project


def refresh_git_project(project):
    if project.source_type != 'git' or not project.repo_url:
        raise RuntimeError('Project is not Git-backed')
    return create_git_project(
        project.endpoint, project.name, project.repo_url,
        project.repo_ref or 'main', project.compose_path or 'compose.yaml',
    )
