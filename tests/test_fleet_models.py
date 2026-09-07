import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from config import create_app, db
from models import ComposeProject, DeploymentRevision, Endpoint
from services.fleet_service import endpoint_health, list_containers, normalize_container


class FleetModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['SECRET_KEY'] = 'test-only'
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_json_fields_and_revision(self):
        with self.app.app_context():
            endpoint = Endpoint(name='test-agent', kind='agent', url='https://127.0.0.1:9002')
            db.session.add(endpoint)
            db.session.flush()
            project = ComposeProject(endpoint_id=endpoint.id, name='app', working_dir='/opt/app')
            project.config_files = ['/opt/app/compose.yaml']
            project.required_mounts = ['/mnt/data']
            project.healthcheck_statuses = [401]
            db.session.add(project)
            db.session.flush()
            revision = DeploymentRevision(project_id=project.id, revision=1)
            revision.image_state = {'app': {'image_id': 'sha256:abc'}}
            db.session.add(revision)
            db.session.commit()
            self.assertEqual(project.config_files, ['/opt/app/compose.yaml'])
            self.assertEqual(project.required_mounts, ['/mnt/data'])
            self.assertEqual(project.healthcheck_statuses, [401])
            self.assertEqual(revision.image_state['app']['image_id'], 'sha256:abc')

    def test_remote_container_schema_has_dashboard_defaults_and_links(self):
        endpoint = Endpoint(
            name='test-agent',
            kind='agent',
            url='https://agent.internal:9002',
            public_ip='192.0.2.10',
        )

        result = normalize_container(endpoint, {
            'id': 'abc123',
            'name': 'example',
            'status': 'running',
            'image': 'example:latest',
            'created': '2026-09-07 10:00:00',
            'ports': [{'container_port': '80', 'host_port': '8080'}],
        })

        self.assertEqual(result['restart_count'], 0)
        self.assertIsNone(result['image_digest'])
        self.assertEqual(result['ports'][0]['url'], 'http://192.0.2.10:8080')
        self.assertEqual(result['urls'], ['http://192.0.2.10:8080'])

    def test_endpoint_status_uses_measured_health_not_state_hint(self):
        endpoint = Endpoint(name='sleeping-host', kind='agent', state_hint='online')
        self.assertEqual(endpoint.to_dict()['status'], 'unknown')

        endpoint.last_checked = datetime.utcnow()
        endpoint.last_error = 'connection timed out'
        self.assertEqual(endpoint.to_dict()['status'], 'offline')

        endpoint.last_error = None
        endpoint.last_seen = endpoint.last_checked
        self.assertEqual(endpoint.to_dict()['status'], 'online')

    def test_failed_live_health_marks_endpoint_offline(self):
        with self.app.app_context():
            endpoint = Endpoint(
                name='powered-off',
                kind='agent',
                url='https://192.0.2.30:9002',
            )
            db.session.add(endpoint)
            db.session.commit()
            with patch('services.fleet_service._agent') as agent:
                agent.return_value.get.side_effect = RuntimeError('connection timed out')
                with self.assertRaisesRegex(RuntimeError, 'timed out'):
                    endpoint_health(endpoint, timeout=1)

            db.session.refresh(endpoint)
            self.assertIsNotNone(endpoint.last_checked)
        self.assertEqual(endpoint.to_dict()['status'], 'offline')

    def test_failed_inventory_marks_endpoint_offline(self):
        with self.app.app_context():
            endpoint = Endpoint(
                name='sleeping-host',
                kind='agent',
                url='https://sleeping.invalid:9002',
                enabled=True,
            )
            db.session.add(endpoint)
            db.session.commit()

            with patch('services.fleet_service._agent') as agent:
                agent.return_value.get.side_effect = RuntimeError('powered off')
                with self.assertRaisesRegex(RuntimeError, 'powered off'):
                    list_containers(endpoint)

            db.session.refresh(endpoint)
            self.assertEqual(endpoint.to_dict()['status'], 'offline')
            self.assertIsNotNone(endpoint.last_checked)


if __name__ == '__main__':
    unittest.main()
