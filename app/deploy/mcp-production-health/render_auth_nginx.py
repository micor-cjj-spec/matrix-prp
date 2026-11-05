"""Render an independent auth vhost candidate. Never installs/reloads Nginx."""
import re
from contract import REALM


def render(*, port=443, upstream=18084, cert='/etc/nginx/ssl/auth.micor.top/fullchain.pem',
           key='/etc/nginx/ssl/auth.micor.top/privkey.pem'):
    if port not in (443, 18446) or upstream not in (18084, 18080):
        raise ValueError('Only production-candidate or disposable loopback ports')
    for path in (cert, key):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path) or '..' in path.split('/'):
            raise ValueError('Fixed absolute certificate path required')
    lines = [f'server {{', f' listen {port} ssl;', f' server_name auth.micor.top;',
        f' ssl_certificate {cert};', f' ssl_certificate_key {key};',
        ' ssl_protocols TLSv1.2 TLSv1.3;', ' ssl_session_tickets off;',
        ' if ($ssl_server_name != auth.micor.top) { return 421; }',
        ' if ($host != auth.micor.top) { return 421; }',
        ' if ($http_host !~* "^auth\\.micor\\.top(?::443)?$") { return 421; }',
        ' if ($request_uri ~ "^[^?]*(%|\\\\|//|\\.\\.)") { return 404; }',
        ' client_max_body_size 16k;', ' client_body_timeout 10s;',
        ' access_log off;', ' error_log stderr emerg;',
        ' add_header Strict-Transport-Security "max-age=31536000" always;',
        ' add_header X-Content-Type-Options nosniff always;',
        ' add_header Referrer-Policy no-referrer always;',
        ' proxy_connect_timeout 3s;', ' proxy_read_timeout 15s;', ' proxy_send_timeout 15s;',
        ' proxy_buffer_size 16k;', ' proxy_buffers 4 16k;', ' proxy_busy_buffers_size 32k;',
        ' proxy_set_header Host auth.micor.top;',
        ' proxy_set_header X-Forwarded-Host auth.micor.top;',
        ' proxy_set_header X-Forwarded-Proto https;',
        ' proxy_set_header X-Forwarded-Port 443;',
        ' proxy_set_header X-Forwarded-For $remote_addr;',
        ' proxy_set_header Forwarded "";']
    exact = [f'/.well-known/oauth-authorization-server/realms/{REALM}',
        f'/realms/{REALM}/.well-known/openid-configuration',
        f'/realms/{REALM}/.well-known/oauth-authorization-server']
    for path in exact:
        lines += [f' location = {path} {{', '  if ($request_method != GET) { return 405; }',
                  f'  proxy_pass http://127.0.0.1:{upstream};', ' }']
    for path, verbs in [
        (f'^/realms/{REALM}/protocol/openid-connect/(auth|certs|logout|login-status-iframe\\.html|3p-cookies/(step1|step2)\\.html)$', 'GET'),
        (f'^/realms/{REALM}/protocol/openid-connect/(token|revoke)$', 'POST'),
        (f'^/realms/{REALM}/login-actions/(authenticate|required-action|consent|restart)$', 'GET|POST'),
        ('^/resources/[A-Za-z0-9._-]+/(login|common)/', 'GET|HEAD')]:
        lines += [f' location ~ {path} {{', f'  if ($request_method !~ ^({verbs})$) {{ return 405; }}',
                  f'  proxy_pass http://127.0.0.1:{upstream};', ' }']
    return '\n'.join(lines + [' location / { return 404; }', '}']) + '\n'
