import os
import tempfile
import unittest

from config import create_app, db
from models import ComposeProject, DeploymentRevision, Endpoint
from services.fleet_service import normalize_container


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


if __name__ == '__main__':
    unittest.main()
