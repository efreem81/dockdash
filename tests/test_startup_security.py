import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import text

import config
from config import create_app, db
from init_db import _secure_database_files


class StartupSecurityTests(unittest.TestCase):
    def test_production_requires_secret_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'SECRET_KEY'):
                create_app({'TESTING': False})

    def test_initial_user_requires_password(self):
        with tempfile.TemporaryDirectory() as directory:
            database_uri = f'sqlite:///{os.path.join(directory, "dockdash.db")}'
            with patch.dict(os.environ, {'SECRET_KEY': 'configured'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'DEFAULT_PASSWORD'):
                    create_app({
                        'TESTING': False,
                        'SQLALCHEMY_DATABASE_URI': database_uri,
                    })

    def test_database_permissions_are_private(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = os.path.join(parent, 'data')
            os.mkdir(directory, mode=0o755)
            database = os.path.join(directory, 'dockdash.db')
            with open(database, 'w', encoding='utf-8'):
                pass
            os.chmod(database, 0o644)
            _secure_database_files(directory)
            self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(database).st_mode & 0o777, 0o600)

    def test_health_rejects_missing_schema(self):
        app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
        with app.app_context():
            db.session.execute(text('DROP TABLE operation_job'))
            db.session.commit()
        response = app.test_client().get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['database_ok'])
        self.assertIn('missing table operation_job', response.get_json()['database_schema_errors'])

    def test_startup_without_migrations_rejects_missing_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database_uri = f'sqlite:///{os.path.join(directory, "empty.db")}'
            environment = {
                'SECRET_KEY': 'configured',
                'DOCKDASH_SKIP_DB_INIT': '1',
            }
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'schema is not ready'):
                    create_app({
                        'TESTING': False,
                        'SQLALCHEMY_DATABASE_URI': database_uri,
                    })

    def test_migration_failure_stops_startup(self):
        with patch.object(config, '_run_migrations', side_effect=RuntimeError('migration failed')):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                create_app({
                    'TESTING': True,
                    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
                })


if __name__ == '__main__':
    unittest.main()
