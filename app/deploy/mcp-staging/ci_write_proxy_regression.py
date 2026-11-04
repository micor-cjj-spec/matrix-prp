"""Actual disposable two-hop TLS/Nginx and approval routing, no live services."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time

from approval_routes_pending import render_v2_write_routes
from oauth_proxy_buffers import render_oauth_header_buffers

AUTH = 'auth-e2e.localhost'
PRP = 'prp-test.micor.top'
HITS = []


class Backend(BaseHTTPRequestHandler):
    def do_GET(self): self.answer()
    def do_POST(self): self.answer()
    def log_message(self, *_args): pass
    def answer(self):
        HITS.append((self.command, self.path))
        if self.path.startswith('/headers/'):
            n = int(self.path.rsplit('/', 1)[-1])
            if n not in (1024, 6500, 20000): self.send_error(404); return
            self.send_response(200)
            self.send_header('Set-Cookie', 'synthetic=' + 'x'*n + '; Secure; HttpOnly')
        else:
            self.send_response(401 if self.path.startswith('/api/') else 200)
        self.send_header('X-Synthetic-Upstream', 'yes')
        self.send_header('Content-Length', '0')
        self.end_headers()


def command(args):
    p = subprocess.run(args, capture_output=True, timeout=20)
    if p.returncode: raise RuntimeError('ISOLATED_' + Path(args[0]).name.upper() + '_FAILED')


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]


def run():
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_OS') != 'Linux'
            or not os.environ.get('RUNNER_TEMP')):
        raise RuntimeError('DISPOSABLE_GITHUB_RUNNER_ONLY')
    # The reviewed V2 snippet intentionally fixes its loopback upstream.
    backend = ThreadingHTTPServer(('127.0.0.1', 18082), Backend)
    thread = threading.Thread(target=backend.serve_forever, daemon=True); thread.start()
    process = None
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix='prp-write-proxy-', dir=os.environ['RUNNER_TEMP']) as tmp:
            root = Path(tmp)
            command(['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048', '-days', '1',
                     '-keyout', str(root/'ca.key'), '-out', str(root/'ca.pem'), '-subj', '/CN=CI-only-CA'])
            command(['openssl', 'req', '-nodes', '-newkey', 'rsa:2048', '-keyout', str(root/'leaf.key'),
                     '-out', str(root/'leaf.csr'), '-subj', '/CN='+AUTH])
            (root/'leaf.ext').write_text('subjectAltName=DNS:'+AUTH+',DNS:'+PRP+'\nextendedKeyUsage=serverAuth\n')
            command(['openssl', 'x509', '-req', '-in', str(root/'leaf.csr'), '-CA', str(root/'ca.pem'),
                     '-CAkey', str(root/'ca.key'), '-CAcreateserial', '-days', '1',
                     '-extfile', str(root/'leaf.ext'), '-out', str(root/'leaf.pem')])
            ports = {name: port() for name in ('inner_old', 'inner_fixed', 'outer_old', 'outer_fixed', 'outer_bad_inner', 'prp')}
            if len(set(ports.values())) != len(ports): raise RuntimeError('ISOLATED_PORT_COLLISION')
            cert = f'ssl_certificate {root}/leaf.pem; ssl_certificate_key {root}/leaf.key;'
            blocks = []
            for name in ('inner_old', 'inner_fixed', 'outer_old', 'outer_fixed', 'outer_bad_inner'):
                buffered = name in ('inner_fixed', 'outer_fixed', 'outer_bad_inner')
                if name.startswith('inner'):
                    upstream = 'proxy_pass http://127.0.0.1:18082;'
                else:
                    target = ports['inner_old' if name == 'outer_bad_inner' else 'inner_fixed']
                    upstream = f'''proxy_pass https://127.0.0.1:{target};
                        proxy_ssl_verify on; proxy_ssl_trusted_certificate {root}/ca.pem;
                        proxy_ssl_server_name on; proxy_ssl_name {AUTH};'''
                blocks.append(f'''server {{ listen 127.0.0.1:{ports[name]} ssl;
                    server_name {AUTH}; {cert}
                    if ($host != {AUTH}) {{ return 421; }}
                    {render_oauth_header_buffers() if buffered else ''}
                    location / {{ {upstream} proxy_set_header Host {AUTH}; proxy_buffering off; }}
                }}''')
            blocks.append(f'''server {{ listen 127.0.0.1:{ports['prp']} ssl;
                server_name {PRP}; {cert}
                if ($host != {PRP}) {{ return 421; }}
                if ($ssl_server_name != {PRP}) {{ return 421; }}
                {render_v2_write_routes()}
                location / {{ return 404; }}
            }}''')
            conf = root/'nginx.conf'
            conf.write_text(f'''daemon off; master_process off; worker_processes 1;
                pid {root}/nginx.pid; error_log {root}/error.private.log;
                events {{ worker_connections 128; }}
                http {{ access_log off;
                    map $http_origin $prp_stage_origin_ok {{ default 0; "" 1; "https://{PRP}" 1; }}
                    {''.join(blocks)}
                }}''')
            command(['nginx', '-t', '-c', str(conf)])
            process = subprocess.Popen(['nginx', '-c', str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for value in ports.values():
                deadline = time.monotonic()+5
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1', value), timeout=.3): pass
                        break
                    except OSError:
                        if time.monotonic()>deadline: raise RuntimeError('ISOLATED_STARTUP_TIMEOUT')
                        time.sleep(.1)
            context = ssl.create_default_context(cafile=str(root/'ca.pem'))
            def request(name, path, method='GET', host=None, origin=None):
                sni = PRP if name == 'prp' else AUTH
                class Connection(http.client.HTTPSConnection):
                    def connect(self):
                        self.sock = context.wrap_socket(socket.create_connection(('127.0.0.1', ports[name]), timeout=5), server_hostname=sni)
                connection = Connection(sni, ports[name], timeout=5)
                headers = {'Host': host or sni}
                if origin: headers['Origin'] = origin
                try:
                    connection.request(method, path, headers=headers)
                    response = connection.getresponse(); response.read()
                    return response.status, response.getheader('X-Synthetic-Upstream') == 'yes'
                finally: connection.close()
            for name in ('inner_old', 'inner_fixed', 'outer_old', 'outer_fixed', 'outer_bad_inner'):
                for size in (1024, 6500, 20000):
                    expected = 200 if size == 1024 or size == 6500 and name in ('inner_fixed', 'outer_fixed') else 502
                    assert request(name, '/headers/'+str(size))[0] == expected, 'HEADER_BOUND_OR_SECOND_HOP_REGRESSION'
                    checks.append('header')
            draft = '00000000-0000-4000-8000-00000000000a'
            api = '/api/mcp/approval/drafts/'+draft
            for path, method in [(api, 'GET'), (api+'?probe=synthetic', 'GET'), (api+'/approve', 'POST'), (api+'/reject', 'POST')]:
                before = len(HITS); code, via = request('prp', path, method)
                assert code == 401 and via and len(HITS) == before+1, 'AUTHENTICATED_APPROVAL_ROUTE_NOT_REACHABLE'
                checks.append('approval')
            for path, method in [(api, 'POST'), (api+'/approve', 'GET'), (api+'/reject', 'GET'),
                                 (api, 'HEAD'), (api+'/delete', 'POST'), (api+'/approve/extra', 'POST'),
                                 (api.replace('-', '%2d'), 'GET'), ('/api/mcp/approval/drafts/not-a-uuid', 'GET')]:
                before = len(HITS); code, via = request('prp', path, method)
                assert code in (400, 403, 404, 405) and not via and len(HITS) == before, 'ILLEGAL_APPROVAL_REQUEST_REACHED_UPSTREAM'
                checks.append('denial')
            for kwargs, expected in [({'host': AUTH}, 421), ({'origin': 'https://untrusted.invalid'}, 403)]:
                before = len(HITS); code, via = request('prp', api, **kwargs)
                assert code == expected and not via and len(HITS) == before, 'AUTHORITY_OR_ORIGIN_BOUNDARY_FAILED'
                checks.append('authority')
            print(json.dumps({'disposable_only': True, 'checks': len(checks), 'passed': len(checks),
                              'tls_verification': True, 'real_user_data': False, 'host_reload': False}))
    finally:
        if process:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        backend.shutdown(); backend.server_close(); thread.join(timeout=5)


if __name__ == '__main__': run()
