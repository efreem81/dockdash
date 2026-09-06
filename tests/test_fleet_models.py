import os
import tempfile
import unittest

from config import create_app, db
from models import ComposeProject, DeploymentRevision, Endpoint


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


if __name__ == '__main__':
    unittest.main()
