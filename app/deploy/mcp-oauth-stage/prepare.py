"""Prepare private, persistent loopback-only OAuth lab; never overwrite secrets."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'mcp-oauth'))
from build_realm import build_realm


def capacity():
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(mem['MemAvailable'].split()[0]) * 1024
    free = shutil.disk_usage('/').free
    if available < 2 * 1024**3 or free < 25 * 1024**3:
        raise RuntimeError('Below 2 GiB memory / 25 GiB disk startup threshold')
    return {'available_memory_bytes': available, 'free_disk_bytes': free}


def prepare(state):
    capacity()
    if state != Path('/root/prp-mcp-oauth-stage'):
        raise ValueError('Only the dedicated staging state directory is supported')
    state.mkdir(mode=0o700)
    os.umask(0o077)
    (state / 'certs').mkdir()
    (state / 'realm').mkdir(mode=0o755)
    env = {'OAUTH_STAGE_STATE': str(state), 'OAUTH_DB_PASSWORD': secrets.token_urlsafe(36),
           'OAUTH_ADMIN_PASSWORD': secrets.token_urlsafe(36),
           'OAUTH_USER_PASSWORD': secrets.token_urlsafe(36)}
    with (state / '.env').open('x') as f:
        f.write(''.join(k+'='+v+'\n' for k,v in env.items()))
    realm = build_realm('https://prp-test.micor.top/api/mcp',
                        staging_client_id='prp-pkce-probe',
                        staging_redirect='http://127.0.0.1:8765/callback')
    realm.update({'accessTokenLifespan': 60, 'ssoSessionIdleTimeout': 600,
                  'ssoSessionMaxLifespan': 1800, 'revokeRefreshToken': True,
                  'refreshTokenMaxReuse': 0})
    path = state / 'realm/prp-mcp-realm.json'
    path.write_text(json.dumps(realm, indent=2));path.chmod(0o644)
    def run(args):
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    cert = state / 'certs'
    run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','7',
         '-keyout',str(cert/'ca.key'),'-out',str(cert/'ca.pem'),'-subj','/CN=PRP Private OAuth Stage CA'])
    run(['openssl','req','-new','-newkey','rsa:2048','-nodes','-keyout',str(cert/'leaf.key'),
         '-out',str(cert/'leaf.csr'),'-subj','/CN=auth-test.micor.top'])
    (cert/'leaf.ext').write_text('subjectAltName=DNS:auth-test.micor.top,DNS:prp-test.micor.top\nextendedKeyUsage=serverAuth\n')
    run(['openssl','x509','-req','-in',str(cert/'leaf.csr'),'-CA',str(cert/'ca.pem'),
         '-CAkey',str(cert/'ca.key'),'-CAcreateserial','-out',str(cert/'leaf.pem'),
         '-days','7','-extfile',str(cert/'leaf.ext')])
    # This truststore contains only a public test CA, no private credentials.
    run(['docker','run','--rm','--network','none','-v',str(state)+':/state',
         'prp-mcp-stage-test-builder','keytool','-importcert','-noprompt',
         '-alias','stage-ca','-file','/state/certs/ca.pem','-keystore','/state/stage-ca.jks',
         '-storetype','JKS','-storepass','public-ca-only'])
    (state/'stage-ca.jks').chmod(0o644)
    config = 'server { listen 443 ssl default_server; ssl_reject_handshake on; }\n'
    for host, upstream in [('auth-test.micor.top','keycloak:8080'),
                           ('prp-test.micor.top','prp-mcp-stage-gateway-1:8080')]:
        config += f'''server {{
 listen 443 ssl;
 server_name {host};
 ssl_certificate /etc/nginx/stage-certs/leaf.pem;
 ssl_certificate_key /etc/nginx/stage-certs/leaf.key;
 if ($host != {host}) {{ return 421; }}
 access_log off;
 location / {{
  proxy_pass http://{upstream};
  proxy_set_header Host {host};
  proxy_set_header X-Forwarded-Host {host};
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header X-Forwarded-Port 443;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_buffering off;
 }}
}}
'''
    (state/'tls.conf').write_text(config)
    print(json.dumps({'prepared': True, 'env_mode': '0600', 'capacity': capacity(),
                      'public_listener': False, 'token_lifespan_seconds': 60}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,default=Path('/root/prp-mcp-oauth-stage'))
    prepare(parser.parse_args().state)
