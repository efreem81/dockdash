import os
import unittest
from unittest.mock import patch

from config import create_app, db
from models import Endpoint, User


class DashboardContractTests(unittest.TestCase):
    def setUp(self):
        os.environ['SECRET_KEY'] = 'test-only'
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            user = User(username='operator')
            user.set_password('test-only-password')
            endpoint = Endpoint(
                name='remote',
                kind='agent',
                url='https://agent.invalid:9002',
                public_ip='192.0.2.10',
            )
            db.session.add_all([user, endpoint])
            db.session.commit()
            self.user_id = user.id
            self.endpoint_id = endpoint.id

    def test_dashboard_tolerates_older_agent_without_restart_count(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True
            session['endpoint_id'] = self.endpoint_id

        old_agent_payload = [{
            'id': 'abc123',
            'name': 'example',
            'status': 'running',
            'image': 'example:latest',
            'created': '2026-09-07 10:00:00',
            'compose_project': '',
            'ports': [],
        }]
        with patch('routes.dashboard.list_containers', return_value=old_agent_payload):
            response = client.get('/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'example', response.data)

    def test_all_hosts_dashboard_keeps_reachable_inventory(self):
        with self.app.app_context():
            offline = Endpoint(
                name='sleeping-host',
                kind='agent',
                url='https://sleeping.invalid:9002',
                public_ip='192.0.2.20',
            )
            db.session.add(offline)
            db.session.commit()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True

        def inventory(endpoint, show_all=False, timeout=None):
            del show_all, timeout
            if endpoint.name == 'sleeping-host':
                raise RuntimeError('powered off')
            return [{
                'id': 'abc123',
                'name': 'reachable-container',
                'status': 'running',
                'image': 'example:latest',
                'created': '2026-09-07 10:00:00',
                'compose_project': '',
                'ports': [],
            }]

        with patch('routes.dashboard.list_containers', side_effect=inventory):
            response = client.get('/dashboard?endpoint_id=all')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'All Hosts', response.data)
        self.assertIn(b'reachable-container', response.data)
        self.assertIn(b'sleeping-host', response.data)
        self.assertIn(b'1/2 reachable', response.data)


if __name__ == '__main__':
    unittest.main()
