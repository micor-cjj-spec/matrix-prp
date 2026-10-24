"""Review-only vhosts. Never writes to /etc/nginx or reloads a service."""
import argparse
from pathlib import Path


def render():
    result = '# PENDING administrator DNS/TLS/public-access approval. NOT INSTALLED.\n'
    for host in ('prp-test.micor.top','auth-test.micor.top'):
        if host.startswith('auth-'):
            upstream='https://127.0.0.1:18443'
            denied='location ^~ /admin/ { return 404; }\n    location ^~ /realms/master/ { return 404; }'
            verify='''proxy_ssl_server_name on;
        proxy_ssl_name auth-test.micor.top;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /root/prp-mcp-oauth-stage/certs/ca.pem;'''
        else:
            upstream='http://127.0.0.1:18081';verify='';denied=''
        result+=f'''server {{
    listen 443 ssl;
    server_name {host};
    ssl_certificate /etc/letsencrypt/live/{host}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{host}/privkey.pem;
    if ($host != {host}) {{ return 421; }}
    access_log off;
    {denied}
    location / {{
        proxy_pass {upstream};
        {verify}
        proxy_set_header Host {host};
        proxy_set_header X-Forwarded-Host {host};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 75s;
    }}
}}
'''
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if str(args.output.resolve()).startswith('/etc/'):
        raise SystemExit('Review output must remain outside the active /etc tree')
    with args.output.open('x') as f:f.write(render())
