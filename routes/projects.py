"""Compose project inventory and lifecycle routes."""
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from config import db
from models import ComposeProject, DeploymentRevision, Endpoint, OperationJob
from services.fleet_service import get_endpoint
from services.project_service import (
    create_git_project, create_managed_project, queue_project_action,
    refresh_git_project, sync_projects,
)

projects_bp = Blueprint('projects', __name__)


def _project_for_request(project_id, data=None):
    """Resolve a project only within the explicitly/currently selected endpoint."""
    endpoint_id = data.get('endpoint_id') if isinstance(data, dict) else None
    endpoint = get_endpoint(endpoint_id)
    return ComposeProject.query.filter_by(
        id=project_id,
        endpoint_id=endpoint.id,
    ).first_or_404()


@projects_bp.get('/projects')
@login_required
def projects():
    endpoint = get_endpoint(remember=True)
    endpoints = Endpoint.query.filter_by(enabled=True).order_by(Endpoint.name).all()
    items = ComposeProject.query.filter_by(endpoint_id=endpoint.id).order_by(ComposeProject.name).all()
    jobs = OperationJob.query.filter_by(endpoint_id=endpoint.id).order_by(OperationJob.id.desc()).limit(30).all()
    return render_template('projects.html', endpoint=endpoint, endpoints=endpoints, projects=items, jobs=jobs)


@projects_bp.post('/api/projects/discover')
@login_required
def api_discover_projects():
    endpoint = get_endpoint(remember=True)
    try:
        items = sync_projects(endpoint)
        return jsonify(success=True, projects=[item.to_dict() for item in items])
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 502


@projects_bp.get('/api/projects')
@login_required
def api_projects():
    endpoint = get_endpoint(remember=True)
    items = ComposeProject.query.filter_by(endpoint_id=endpoint.id).order_by(ComposeProject.name).all()
    return jsonify(success=True, projects=[item.to_dict() for item in items])


@projects_bp.get('/api/projects/<int:project_id>')
@login_required
def api_project(project_id):
    project = _project_for_request(project_id)
    revisions = DeploymentRevision.query.filter_by(project_id=project.id).order_by(DeploymentRevision.revision.desc()).limit(20).all()
    return jsonify(success=True, project=project.to_dict(), revisions=[item.to_dict() for item in revisions])


@projects_bp.put('/api/projects/<int:project_id>')
@login_required
def api_update_project(project_id):
    data = request.get_json() or {}
    project = _project_for_request(project_id, data)
    if 'required_mounts' in data:
        mounts = data.get('required_mounts') or []
        if not isinstance(mounts, list):
            return jsonify(success=False, error='required_mounts must be a list'), 400
        project.required_mounts = mounts
    if 'healthcheck_url' in data:
        project.healthcheck_url = (data.get('healthcheck_url') or '').strip() or None
    if 'healthcheck_statuses' in data:
        try:
            statuses = [int(value) for value in (data.get('healthcheck_statuses') or [])]
        except (TypeError, ValueError):
            return jsonify(success=False, error='healthcheck_statuses must contain integers'), 400
        if any(value < 100 or value > 599 for value in statuses):
            return jsonify(success=False, error='healthcheck statuses must be between 100 and 599'), 400
        project.healthcheck_statuses = sorted(set(statuses))
    if 'healthcheck_timeout' in data:
        project.healthcheck_timeout = max(5, min(1800, int(data['healthcheck_timeout'])))
    db.session.commit()
    return jsonify(success=True, project=project.to_dict())


@projects_bp.post('/api/projects/<int:project_id>/action')
@login_required
def api_project_action(project_id):
    data = request.get_json() or {}
    project = _project_for_request(project_id, data)
    data.pop('endpoint_id', None)
    action = data.pop('action', None)
    allowed = {'validate', 'start', 'stop', 'restart', 'pull', 'up', 'recreate', 'logs', 'scale', 'down'}
    if action not in allowed:
        return jsonify(success=False, error='Unsupported project action'), 400
    try:
        job = queue_project_action(
            current_app._get_current_object(), project, action,
            current_user.username, options=data,
        )
    except (TypeError, ValueError) as exc:
        return jsonify(success=False, error=str(exc)), 400
    return jsonify(success=True, job=job.to_dict()), 202


@projects_bp.get('/api/jobs/<int:job_id>')
@login_required
def api_job(job_id):
    endpoint = get_endpoint()
    job = OperationJob.query.filter_by(id=job_id, endpoint_id=endpoint.id).first_or_404()
    return jsonify(success=True, job=job.to_dict())


@projects_bp.get('/api/jobs')
@login_required
def api_jobs():
    endpoint = get_endpoint()
    jobs = OperationJob.query.filter_by(endpoint_id=endpoint.id).order_by(OperationJob.id.desc()).limit(100).all()
    return jsonify(success=True, jobs=[job.to_dict() for job in jobs])


@projects_bp.post('/api/projects/managed')
@login_required
def api_managed_project():
    data = request.get_json() or {}
    endpoint = get_endpoint(data.get('endpoint_id'), remember=True)
    try:
        project = create_managed_project(
            endpoint, (data.get('name') or '').strip(), data.get('compose_content') or '',
            healthcheck_url=(data.get('healthcheck_url') or '').strip() or None,
            required_mounts=data.get('required_mounts') or [],
            healthcheck_statuses=data.get('healthcheck_statuses') or [],
        )
        return jsonify(success=True, project=project.to_dict()), 201
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400


@projects_bp.post('/api/projects/git')
@login_required
def api_git_project():
    data = request.get_json() or {}
    endpoint = get_endpoint(data.get('endpoint_id'), remember=True)
    try:
        project = create_git_project(
            endpoint, (data.get('name') or '').strip(), (data.get('repo_url') or '').strip(),
            (data.get('repo_ref') or 'main').strip(), (data.get('compose_path') or 'compose.yaml').strip(),
        )
        return jsonify(success=True, project=project.to_dict()), 201
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400


@projects_bp.post('/api/projects/<int:project_id>/git-update')
@login_required
def api_git_update(project_id):
    data = request.get_json() or {}
    project = _project_for_request(project_id, data)
    try:
        project = refresh_git_project(project)
        return jsonify(success=True, project=project.to_dict())
    except Exception as exc:
        return jsonify(success=False, error=str(exc)), 400
