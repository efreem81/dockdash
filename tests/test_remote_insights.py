import os
import unittest
from unittest.mock import patch

from config import create_app, db
from models import Endpoint, User
from services.update_service import get_stored_updates
from services.vulnerability_service import get_stored_vulnerabilities


class RemoteInsightRouteTests(unittest.TestCase):
    def setUp(self):
        os.environ['SECRET_KEY'] = 'test-only'
        self.app = create_app({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            user = User(username='operator')
            user.set_password('test-only-password')
            endpoint = Endpoint(name='remote', kind='agent', url='https://agent.invalid:9002')
            db.session.add_all([user, endpoint])
            db.session.commit()
            self.user_id = user.id
            self.endpoint_id = endpoint.id

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True

    def test_remote_update_results_are_persisted_for_endpoint(self):
        result = {
            'image': 'example:latest',
            'has_update': True,
            'local_digest': 'sha256:old',
            'remote_digest': 'sha256:new',
            'error': None,
        }
        with patch('routes.images.check_endpoint_updates', return_value={
            'success': True,
            'results': {'example:latest': result},
        }):
            response = self.client.post(
                f'/api/images/check-updates?endpoint_id={self.endpoint_id}',
                json={'images': ['example:latest']},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['results']['example:latest']['has_update'])
        with self.app.app_context():
            stored = get_stored_updates(endpoint_id=self.endpoint_id)
            self.assertTrue(stored['example:latest']['has_update'])
            self.assertEqual(get_stored_updates(), {})

    def test_remote_scan_results_are_persisted_for_endpoint(self):
        scan = {
            'image': 'example:latest',
            'success': True,
            'scanner': 'trivy',
            'vulnerabilities': [],
            'summary': {'critical': 1, 'high': 2, 'medium': 0, 'low': 0, 'unknown': 0, 'total': 3},
            'error': None,
        }
        with patch('routes.vulnerabilities.scan_endpoint_images', return_value={
            'success': True,
            'results': {'example:latest': scan},
            'total_summary': scan['summary'],
            'images_scanned': 1,
        }):
            response = self.client.post(
                f'/api/vulnerabilities/scan-all?endpoint_id={self.endpoint_id}',
                json={},
            )

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            stored = get_stored_vulnerabilities(endpoint_id=self.endpoint_id)
            self.assertEqual(stored['example:latest']['critical'], 1)
            self.assertEqual(get_stored_vulnerabilities(), {})

    def test_container_detail_scan_uses_owning_agent_and_persists_result(self):
        scan = {
            'image': 'example:latest',
            'success': True,
            'scanner': 'trivy',
            'vulnerabilities': [],
            'summary': {
                'critical': 0, 'high': 1, 'medium': 0,
                'low': 0, 'unknown': 0, 'total': 1,
            },
            'error': None,
        }
        with patch('routes.vulnerabilities.fleet_container_detail', return_value={
            'id': 'abc123', 'name': 'web', 'image': 'example:latest',
        }), patch('routes.vulnerabilities.scan_endpoint_images', return_value=scan):
            response = self.client.post(
                f'/api/vulnerabilities/scan-container/abc123?endpoint_id={self.endpoint_id}',
                json={'force': True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        with self.app.app_context():
            stored = get_stored_vulnerabilities(endpoint_id=self.endpoint_id)
            self.assertEqual(stored['example:latest']['high'], 1)


if __name__ == '__main__':
    unittest.main()
