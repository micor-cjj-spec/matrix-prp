"""Review-only rendering of the existing isolated two-SNI TLS gateway.

Public PRP V2 traffic must use its separate loopback gateway, never this legacy
PRP SNI. Its preservation here records the installed topology, not a V2 route.
"""
from check_env import check
from oauth_proxy_buffers import render_oauth_header_buffers


def render(config):
    validated = check(config)
    stage, auth = validated['stage_host'], validated['oauth_host']
    if stage == auth:
        raise ValueError('Distinct staging SNI required')
    return f'''# REVIEW ONLY; no installation or reload is performed.
server {{ listen 443 ssl default_server; ssl_reject_handshake on; }}
server {{
    listen 443 ssl;
    server_name {auth};
{render_oauth_header_buffers()}
    ssl_certificate /etc/nginx/stage-certs/leaf.pem;
    ssl_certificate_key /etc/nginx/stage-certs/leaf.key;
    if ($host != {auth}) {{ return 421; }}
    access_log off;
    error_log /dev/null crit;
    location / {{
        proxy_pass http://keycloak:8080;
        proxy_set_header Host {auth};
        proxy_set_header X-Forwarded-Host {auth};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;
    }}
}}
server {{
    listen 443 ssl;
    server_name {stage};
    ssl_certificate /etc/nginx/stage-certs/leaf.pem;
    ssl_certificate_key /etc/nginx/stage-certs/leaf.key;
    if ($host != {stage}) {{ return 421; }}
    access_log off;
    error_log /dev/null crit;
    location / {{
        proxy_pass http://prp-mcp-stage-gateway-1:8080;
        proxy_set_header Host {stage};
        proxy_set_header X-Forwarded-Host {stage};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;
    }}
}}
'''
