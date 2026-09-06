import os
import unittest

from config import create_app, db
from models import Endpoint
from services.fleet_service import EndpointSelectionError, get_endpoint


class EndpointSelectionTests(unittest.TestCase):
    def setUp(self):
        os.environ['SECRET_KEY'] = 'test-only'
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            endpoint = Endpoint(name='default', kind='local', enabled=True)
            db.session.add(endpoint)
            db.session.commit()
            self.endpoint_id = endpoint.id

    def test_explicit_unknown_endpoint_fails_closed(self):
        with self.app.app_context(), self.app.test_request_context('/?endpoint_id=99999'):
            with self.assertRaisesRegex(EndpointSelectionError, 'not found'):
                get_endpoint()

    def test_explicit_disabled_endpoint_fails_closed(self):
        with self.app.app_context():
            endpoint = db.session.get(Endpoint, self.endpoint_id)
            endpoint.enabled = False
            db.session.commit()
            with self.app.test_request_context(f'/?endpoint_id={self.endpoint_id}'):
                with self.assertRaisesRegex(EndpointSelectionError, 'disabled'):
                    get_endpoint()


if __name__ == '__main__':
    unittest.main()
