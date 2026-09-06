import unittest
from types import SimpleNamespace

from services.agent_client import AgentClient, AgentError


class AgentClientTests(unittest.TestCase):
    def test_rejects_plaintext_endpoint(self):
        endpoint = SimpleNamespace(url='http://127.0.0.1:9002')
        with self.assertRaisesRegex(AgentError, 'HTTPS'):
            AgentClient(endpoint)

    def test_rejects_url_credentials(self):
        endpoint = SimpleNamespace(url='https://user:password@127.0.0.1:9002')
        with self.assertRaisesRegex(AgentError, 'embedded credentials'):
            AgentClient(endpoint)


if __name__ == '__main__':
    unittest.main()
