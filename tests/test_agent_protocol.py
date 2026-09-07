import importlib.util
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class AgentProtocolTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        os.environ['DOCKDASH_COMPOSE_ROOTS'] = self.root.name
        os.environ['DOCKDASH_MANAGED_ROOT'] = os.path.join(self.root.name, 'managed')
        spec = importlib.util.spec_from_file_location(
            'dockdash_agent_protocol',
            os.path.join(os.path.dirname(__file__), '..', 'agent', 'app.py'),
        )
        self.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent)

    def tearDown(self):
        self.root.cleanup()

    def test_remote_exec_is_not_exposed(self):
        response = self.agent.app.test_client().post('/v1/containers/agent/exec', json={
            'command': ['/bin/sh'],
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()['success'])

    def test_container_info_includes_dashboard_restart_fields(self):
        container = SimpleNamespace(
            id='a' * 64,
            short_id='a' * 12,
            name='example',
            status='running',
            image=SimpleNamespace(id='sha256:image', tags=['example:latest']),
            attrs={
                'Created': '2026-09-07T10:00:00Z',
                'RestartCount': 3,
                'Config': {'Image': 'example:latest', 'Labels': {}, 'Env': []},
                'State': {'ExitCode': 0},
                'NetworkSettings': {'Ports': {}, 'Networks': {}},
                'Mounts': [],
            },
        )

        result = self.agent.container_info(container)

        self.assertEqual(result['id'], container.id)
        self.assertEqual(result['full_id'], container.id)
        self.assertEqual(result['restart_count'], 3)
        self.assertEqual(result['exit_code'], 0)

    def test_default_health_policy_rejects_404(self):
        response = SimpleNamespace(status_code=404)
        with patch.object(self.agent.requests, 'get', return_value=response), \
                patch.object(self.agent.time, 'time', side_effect=[0, 0, 6]), \
                patch.object(self.agent.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
                self.agent.check_application({
                    'healthcheck_url': 'http://service.invalid/health',
                    'healthcheck_timeout': 5,
                })

    def test_explicit_health_status_can_allow_auth_challenge(self):
        response = SimpleNamespace(status_code=401)
        with patch.object(self.agent.requests, 'get', return_value=response):
            result = self.agent.check_application({
                'healthcheck_url': 'http://service.invalid/',
                'healthcheck_statuses': [401],
            })
        self.assertEqual(result['status_code'], 401)

    def test_failed_git_validation_preserves_active_checkout(self):
        active = os.path.join(self.agent.MANAGED_ROOT, 'sample')
        os.makedirs(os.path.join(active, '.git'))
        marker = os.path.join(active, 'active-marker')
        with open(marker, 'w', encoding='utf-8') as handle:
            handle.write('original')

        def fake_run(args, cwd=None, timeout=600):
            del cwd, timeout
            if args[:2] == ['git', 'clone']:
                staging = args[-1]
                os.makedirs(os.path.join(staging, '.git'))
                with open(os.path.join(staging, 'compose.yaml'), 'w', encoding='utf-8') as handle:
                    handle.write('services: {}\n')
            return ''

        with patch.object(self.agent, 'run', side_effect=fake_run), \
                patch.object(self.agent, 'preflight', side_effect=RuntimeError('invalid Compose')):
            response = self.agent.app.test_client().post('/v1/projects/git', json={
                'name': 'sample',
                'repo_url': 'https://example.invalid/sample.git',
                'repo_ref': 'main',
                'compose_path': 'compose.yaml',
            })
        self.assertEqual(response.status_code, 500)
        self.assertTrue(os.path.isfile(marker))
        with open(marker, encoding='utf-8') as handle:
            self.assertEqual(handle.read(), 'original')


if __name__ == '__main__':
    unittest.main()
