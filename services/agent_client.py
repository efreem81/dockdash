"""HTTP client for the mutually authenticated DockDash agent protocol."""
from __future__ import annotations

import os
from urllib.parse import urljoin, urlparse

import requests


class AgentError(RuntimeError):
    pass


class AgentClient:
    def __init__(self, endpoint):
        if not endpoint.url:
            raise AgentError('Agent endpoint URL is not configured')
        parsed = urlparse(endpoint.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise AgentError('Agent endpoint must be an HTTPS URL without embedded credentials')
        self.base_url = endpoint.url.rstrip('/') + '/'
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pki')
        ca = os.environ.get('DOCKDASH_AGENT_CA', os.path.join(data_dir, 'ca.crt'))
        cert = os.environ.get('DOCKDASH_AGENT_CERT', os.path.join(data_dir, 'controller.crt'))
        key = os.environ.get('DOCKDASH_AGENT_KEY', os.path.join(data_dir, 'controller.key'))
        if not all(os.path.isfile(path) for path in (ca, cert, key)):
            raise AgentError('DockDash controller mTLS files are missing')
        self.verify = ca
        self.cert = (cert, key)
        self.timeout = int(os.environ.get('DOCKDASH_AGENT_TIMEOUT', '30'))

    def request(self, method, path, *, params=None, json=None, timeout=None):
        try:
            response = requests.request(
                method,
                urljoin(self.base_url, path.lstrip('/')),
                params=params,
                json=json,
                verify=self.verify,
                cert=self.cert,
                timeout=timeout or self.timeout,
                allow_redirects=False,
            )
            payload = response.json()
        except requests.RequestException as exc:
            raise AgentError(str(exc)) from exc
        except ValueError as exc:
            raise AgentError('Agent returned a non-JSON response') from exc
        if response.status_code >= 400 or not payload.get('success', True):
            raise AgentError(payload.get('error') or f'Agent returned HTTP {response.status_code}')
        return payload

    def get(self, path, **kwargs):
        return self.request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self.request('POST', path, **kwargs)
