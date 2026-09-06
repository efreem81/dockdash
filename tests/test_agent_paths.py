import importlib.util
import os
import tempfile
import unittest


class AgentPathTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        os.environ['DOCKDASH_COMPOSE_ROOTS'] = self.root.name
        os.environ['DOCKDASH_MANAGED_ROOT'] = os.path.join(self.root.name, 'managed')
        spec = importlib.util.spec_from_file_location('dockdash_agent', os.path.join(os.path.dirname(__file__), '..', 'agent', 'app.py'))
        self.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent)

    def tearDown(self):
        self.root.cleanup()

    def test_allows_configured_root(self):
        path = os.path.join(self.root.name, 'app', 'compose.yaml')
        self.assertEqual(self.agent.allowed_path(path), os.path.realpath(path))

    def test_rejects_outside_root(self):
        with self.assertRaises(ValueError):
            self.agent.allowed_path('/etc/shadow')

    def test_rejects_symlink_escape(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        link = os.path.join(self.root.name, 'escaped')
        os.symlink(outside.name, link)
        with self.assertRaises(ValueError):
            self.agent.allowed_path(os.path.join(link, 'compose.yaml'))


if __name__ == '__main__':
    unittest.main()
