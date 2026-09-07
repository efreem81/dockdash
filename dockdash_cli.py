"""Small administrative CLI for deployment automation."""
import argparse
import time
from urllib.parse import urlparse

from config import create_app, db
from models import ComposeProject, Endpoint
from services.agent_client import AgentClient
from services.fleet_service import endpoint_health
from services.project_service import queue_project_action, run_worker, sync_projects


def endpoint_add(args):
    if args.kind == 'agent':
        parsed = urlparse(args.url or '')
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise SystemExit('agent URL must be HTTPS and may not contain embedded credentials')
    endpoint = Endpoint.query.filter_by(name=args.name).first()
    if not endpoint:
        endpoint = Endpoint(name=args.name)
        db.session.add(endpoint)
    endpoint.kind = args.kind
    endpoint.url = args.url
    endpoint.public_ip = args.public_ip
    endpoint.state_hint = args.state_hint
    endpoint.enabled = True
    db.session.commit()
    print(f'endpoint {endpoint.id}: {endpoint.name}')


def endpoint_list(_args):
    for endpoint in Endpoint.query.order_by(Endpoint.id):
        print(
            f'{endpoint.id}\t{endpoint.name}\t{endpoint.kind}\t'
            f'{endpoint.url or "-"}\t{endpoint.to_dict()["status"]}'
        )


def _endpoint_by_name(name):
    endpoint = Endpoint.query.filter_by(name=name).first()
    if not endpoint:
        raise SystemExit(f'endpoint not found: {name}')
    return endpoint


def endpoint_test(args):
    endpoint = _endpoint_by_name(args.name)
    result = endpoint_health(endpoint)['system']
    print(f'{endpoint.name}: {result.get("name")} Docker {result.get("docker_version")} ({result.get("containers_running")} running)')


def project_sync(args):
    endpoint = _endpoint_by_name(args.endpoint)
    projects = sync_projects(endpoint)
    print(f'{endpoint.name}: adopted {len(projects)} Compose projects')


def project_validate(args):
    endpoint = _endpoint_by_name(args.endpoint)
    project = ComposeProject.query.filter_by(endpoint_id=endpoint.id, name=args.project).first()
    if not project:
        raise SystemExit(f'project not found: {args.endpoint}/{args.project}')
    result = AgentClient(endpoint).post('/v1/projects/action', json={
        'name': project.name,
        'working_dir': project.working_dir,
        'config_files': project.config_files,
        'required_mounts': project.required_mounts,
        'action': 'validate',
    }, timeout=120)
    if not result.get('success'):
        raise SystemExit('validation failed')
    print(f'{endpoint.name}/{project.name}: valid')


def project_action(args):
    endpoint = _endpoint_by_name(args.endpoint)
    project = ComposeProject.query.filter_by(endpoint_id=endpoint.id, name=args.project).first()
    if not project:
        raise SystemExit(f'project not found: {args.endpoint}/{args.project}')
    job = queue_project_action(app, project, args.action, 'dockdash-cli')
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        db.session.expire_all()
        current = db.session.get(type(job), job.id)
        if current.status in {'succeeded', 'failed'}:
            if current.status == 'failed':
                raise SystemExit(f'job {current.id} failed: {current.error}')
            print(f'job {current.id}: {endpoint.name}/{project.name} {args.action} succeeded')
            return
        time.sleep(0.5)
    raise SystemExit(f'job {job.id} did not finish within {args.timeout} seconds')


def job_worker(args):
    print('DockDash operation worker started', flush=True)
    run_worker(app, once=args.once, poll_interval=args.poll_interval)


parser = argparse.ArgumentParser(description='DockDash administration')
sub = parser.add_subparsers(dest='command', required=True)
add = sub.add_parser('endpoint-add')
add.add_argument('--name', required=True)
add.add_argument('--kind', choices=('local', 'agent'), default='agent')
add.add_argument('--url')
add.add_argument('--public-ip')
add.add_argument('--state-hint', choices=('online', 'offline', 'asleep', 'maintenance'), default='online')
add.set_defaults(func=endpoint_add)
listing = sub.add_parser('endpoint-list')
listing.set_defaults(func=endpoint_list)
test = sub.add_parser('endpoint-test')
test.add_argument('--name', required=True)
test.set_defaults(func=endpoint_test)
sync = sub.add_parser('project-sync')
sync.add_argument('--endpoint', required=True)
sync.set_defaults(func=project_sync)
validate = sub.add_parser('project-validate')
validate.add_argument('--endpoint', required=True)
validate.add_argument('--project', required=True)
validate.set_defaults(func=project_validate)
action = sub.add_parser('project-action')
action.add_argument('--endpoint', required=True)
action.add_argument('--project', required=True)
action.add_argument('--action', choices=('validate', 'start', 'stop', 'restart', 'pull', 'up', 'recreate', 'update', 'logs', 'scale', 'down'), default='validate')
action.add_argument('--timeout', type=int, default=180)
action.set_defaults(func=project_action)
worker = sub.add_parser('job-worker')
worker.add_argument('--once', action='store_true')
worker.add_argument('--poll-interval', type=float, default=1.0)
worker.set_defaults(func=job_worker)

if __name__ == '__main__':
    arguments = parser.parse_args()
    app = create_app()
    with app.app_context():
        arguments.func(arguments)
