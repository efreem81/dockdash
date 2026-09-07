import os
import tempfile
import unittest

from config import create_app, db
from models import ComposeProject, Endpoint, OperationJob, User


class ProjectRouteIsolationTests(unittest.TestCase):
    def setUp(self):
        os.environ['SECRET_KEY'] = 'test-only'
        self.database_directory = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.database_directory.name, 'routes.db')
        self.app = create_app({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_path}',
        })
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            user = User(username='reviewer')
            user.set_password('test-only')
            first = Endpoint(name='first', kind='agent', url='https://first:9002')
            second = Endpoint(name='second', kind='agent', url='https://second:9002')
            db.session.add_all([user, first, second])
            db.session.flush()
            project = ComposeProject(
                endpoint_id=first.id,
                name='app',
                working_dir='/opt/app',
            )
            db.session.add(project)
            db.session.flush()
            job = OperationJob(
                endpoint_id=first.id,
                project_id=project.id,
                action='validate',
                status='queued',
            )
            db.session.add(job)
            db.session.commit()
            self.user_id = user.id
            self.first_id = first.id
            self.second_id = second.id
            self.project_id = project.id
            self.job_id = job.id

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
        self.database_directory.cleanup()

    def test_action_rejects_project_from_another_endpoint(self):
        response = self.client.post(
            f'/api/projects/{self.project_id}/action',
            json={'action': 'down', 'endpoint_id': self.second_id},
        )
        self.assertEqual(response.status_code, 404)
        with self.app.app_context():
            self.assertEqual(OperationJob.query.count(), 1)

    def test_project_and_job_reads_are_endpoint_scoped(self):
        project_response = self.client.get(
            f'/api/projects/{self.project_id}?endpoint_id={self.second_id}'
        )
        job_response = self.client.get(
            f'/api/jobs/{self.job_id}?endpoint_id={self.second_id}'
        )
        self.assertEqual(project_response.status_code, 404)
        self.assertEqual(job_response.status_code, 404)

    def test_action_queues_on_matching_endpoint(self):
        response = self.client.post(
            f'/api/projects/{self.project_id}/action',
            json={'action': 'validate', 'endpoint_id': self.first_id},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()['job']['endpoint_id'], self.first_id)

    def test_update_action_accepts_only_service_selection(self):
        response = self.client.post(
            f'/api/projects/{self.project_id}/action',
            json={
                'action': 'update',
                'endpoint_id': self.first_id,
                'services': ['web'],
            },
        )
        self.assertEqual(response.status_code, 202)
        with self.app.app_context():
            job = db.session.get(OperationJob, response.get_json()['job']['id'])
            self.assertEqual(job.action, 'update')
            self.assertEqual(job.request_json, '{"services": ["web"]}')


if __name__ == '__main__':
    unittest.main()
