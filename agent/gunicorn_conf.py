"""TLS-only Gunicorn configuration for the DockDash agent."""
import ssl


bind = '0.0.0.0:9002'
workers = 2
timeout = 1800
certfile = '/certs/server.crt'
keyfile = '/certs/server.key'
ca_certs = '/certs/ca.crt'
cert_reqs = ssl.CERT_REQUIRED
ciphers = 'ECDHE+AESGCM:ECDHE+CHACHA20'


def ssl_context(_conf, default_ssl_context_factory):
    """Require modern encrypted transport while retaining TLS 1.3 support."""
    context = default_ssl_context_factory()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    return context
