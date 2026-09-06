import json
import os
import unittest
from unittest.mock import patch

from config import create_app, db
from models import ComposeProject, Endpoint, OperationJob
from services.project_service import (
    claim_next_job,
    queue_project_action,
    recover_interrupted_jobs,
    run_claimed_job,
    sanitize_action_options,
)


class ProjectJobTests(unittest.TestCase):
    def setUp(self):
        os.environ['SECRET_KEY'] = 'test-only'
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        endpoint = Endpoint(name='agent', kind='agent', url='https://agent:9002')
        db.session.add(endpoint)
        db.session.flush()
        self.project = ComposeProject(
            endpoint_id=endpoint.id,
            name='app',
            working_dir='/opt/app',
        )
        self.project.config_files = ['/opt/app/compose.yaml']
        db.session.add(self.project)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def test_authoritative_project_fields_cannot_be_overridden(self):
        with self.assertRaisesRegex(ValueError, 'working_dir'):
            sanitize_action_options('up', {'working_dir': '/opt/other'})

    def test_queue_is_durable_and_not_executed_inline(self):
        job = queue_project_action(self.app, self.project, 'validate', 'tester')
        self.assertEqual(job.status, 'queued')
        self.assertIsNone(job.started_at)

    def test_worker_recovers_and_executes_one_job(self):
        interrupted = OperationJob(
            endpoint_id=self.project.endpoint_id,
            project_id=self.project.id,
            action='validate',
            status='running',
        )
        waiting = OperationJob(
            endpoint_id=self.project.endpoint_id,
            project_id=self.project.id,
            action='validate',
            status='queued',
        )
        db.session.add_all([interrupted, waiting])
        db.session.commit()
        self.assertEqual(recover_interrupted_jobs(), 1)
        job_id = claim_next_job()
        self.assertEqual(job_id, interrupted.id)

        class FakeClient:
            def post(self, _path, json=None, timeout=None):
                self.payload = json
                return {'state': {'config_digest': 'after', 'images': {}}, 'output': 'ok'}

        fake_client = FakeClient()
        with patch('services.project_service.project_state', return_value={
            'config_digest': 'before', 'images': {},
        }), patch('services.project_service._client', return_value=fake_client):
            self.assertTrue(run_claimed_job(job_id))
        db.session.expire_all()
        completed = db.session.get(OperationJob, job_id)
        self.assertEqual(completed.status, 'succeeded')
        self.assertEqual(fake_client.payload['working_dir'], '/opt/app')
        self.assertNotIn('working_dir', json.loads(completed.request_json))
        self.assertEqual(db.session.get(OperationJob, waiting.id).status, 'queued')

    def test_malformed_job_fails_without_blocking_queue(self):
        malformed = OperationJob(
            endpoint_id=self.project.endpoint_id,
            project_id=self.project.id,
            action='validate',
            status='queued',
            request_json='{invalid',
        )
        waiting = OperationJob(
            endpoint_id=self.project.endpoint_id,
            project_id=self.project.id,
            action='validate',
            status='queued',
        )
        db.session.add_all([malformed, waiting])
        db.session.commit()

        self.assertEqual(claim_next_job(), malformed.id)
        self.assertFalse(run_claimed_job(malformed.id))
        db.session.expire_all()
        failed = db.session.get(OperationJob, malformed.id)
        self.assertEqual(failed.status, 'failed')
        self.assertIn('Expecting property name', failed.error)
        self.assertEqual(claim_next_job(), waiting.id)

    def test_job_rejects_project_endpoint_mismatch(self):
        other_endpoint = Endpoint(name='other', kind='agent', url='https://other:9002')
        db.session.add(other_endpoint)
        db.session.flush()
        job = OperationJob(
            endpoint_id=other_endpoint.id,
            project_id=self.project.id,
            action='validate',
            status='running',
        )
        db.session.add(job)
        db.session.commit()

        self.assertFalse(run_claimed_job(job.id))
        self.assertEqual(job.status, 'failed')
        self.assertIn('does not match', job.error)


if __name__ == '__main__':
    unittest.main()
