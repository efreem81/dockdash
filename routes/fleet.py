"""Docker fleet endpoint administration."""
from urllib.parse import urlparse

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from config import db
from models import Endpoint
from services.fleet_service import endpoint_health, get_endpoint

fleet_bp = Blueprint('fleet', __name__)


@fleet_bp.get('/fleet')
@login_required
def fleet():
    endpoints = Endpoint.query.order_by(Endpoint.name).all()
    return render_template('fleet.html', endpoints=endpoints)


@fleet_bp.get('/api/endpoints')
@login_required
def api_endpoints():
    return jsonify(success=True, endpoints=[item.to_dict() for item in Endpoint.query.order_by(Endpoint.name).all()])


@fleet_bp.post('/api/endpoints')
@login_required
def api_create_endpoint():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    kind = (data.get('kind') or 'agent').strip()
    url = (data.get('url') or '').strip() or None
    if not name or kind not in {'local', 'agent'}:
        return jsonify(success=False, error='A name and valid endpoint kind are required'), 400
    parsed = urlparse(url or '')
    if kind == 'agent' and (
        parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
    ):
        return jsonify(success=False, error='Agent endpoints require an HTTPS URL'), 400
    if Endpoint.query.filter_by(name=name).first():
        return jsonify(success=False, error='An endpoint with that name already exists'), 409
    endpoint = Endpoint(
        name=name, kind=kind, url=url,
        public_ip=(data.get('public_ip') or '').strip() or None,
        state_hint=(data.get('state_hint') or 'online').strip(),
    )
    db.session.add(endpoint)
    db.session.commit()
    return jsonify(success=True, endpoint=endpoint.to_dict()), 201


@fleet_bp.put('/api/endpoints/<int:endpoint_id>')
@login_required
def api_update_endpoint(endpoint_id):
    endpoint = db.get_or_404(Endpoint, endpoint_id)
    data = request.get_json() or {}
    for field in ('name', 'url', 'public_ip', 'state_hint'):
        if field in data:
            value = data[field]
            setattr(endpoint, field, value.strip() if isinstance(value, str) else value)
    if endpoint.kind == 'agent':
        parsed = urlparse(endpoint.url or '')
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            db.session.rollback()
            return jsonify(success=False, error='Agent endpoints require an HTTPS URL without embedded credentials'), 400
    if 'enabled' in data:
        endpoint.enabled = bool(data['enabled'])
    db.session.commit()
    return jsonify(success=True, endpoint=endpoint.to_dict())


@fleet_bp.post('/api/endpoints/<int:endpoint_id>/test')
@login_required
def api_test_endpoint(endpoint_id):
    endpoint = db.get_or_404(Endpoint, endpoint_id)
    try:
        result = endpoint_health(endpoint)
        return jsonify(success=True, endpoint=endpoint.to_dict(), system=result.get('system'))
    except Exception as exc:
        return jsonify(success=False, endpoint=endpoint.to_dict(), error=str(exc)), 502


@fleet_bp.post('/api/endpoints/<int:endpoint_id>/select')
@login_required
def api_select_endpoint(endpoint_id):
    endpoint = db.get_or_404(Endpoint, endpoint_id)
    get_endpoint(endpoint.id, remember=True)
    return jsonify(success=True, endpoint=endpoint.to_dict())
