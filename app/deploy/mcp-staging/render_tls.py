#!/usr/bin/env python3
"""Render *review-only* TLS Nginx virtual hosts for PRP MCP staging.

Never installs certificates, reloads Nginx, edits production files or opens ports.
The generated file must be reviewed for collisions with existing server_name rules.
"""
import argparse
from pathlib import Path
from check_env import check, parse_env


def render(config):
    checked = check(config)
    stage = checked["stage_host"]
    auth = checked["oauth_host"]
    if stage == auth:
        raise ValueError("Staging PRP and OAuth hosts must be distinct")
    # Hostnames have already been canonicalized, validated and excluded from
    # the production origin by check_env. Never interpolate arbitrary headers.
    return f"""# GENERATED FOR REVIEW ONLY. DO NOT INSTALL INTO A LIVE SERVER AUTOMATICALLY.
# Requires valid individual certificates at paths below.
# Deploy only after separately confirming no duplicate server_name and preserving
# the existing production micor.top server block and its default_server.
# Both upstreams MUST bind only 127.0.0.1 on this host.
server {{
    listen 443 ssl;
    server_name {stage};
    ssl_certificate /etc/letsencrypt/live/{stage}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{stage}/privkey.pem;
    server_tokens off;
    client_max_body_size 14m;
    if ($host != {stage}) {{ return 421; }}

    location / {{
        proxy_pass http://127.0.0.1:18081;
        proxy_http_version 1.1;
        proxy_set_header Host {stage};
        proxy_set_header X-Forwarded-Host {stage};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 75s;
        proxy_cache off;
    }}
}}

# Authorization server is a SEPARATE staging-only Keycloak instance.
server {{
    listen 443 ssl;
    server_name {auth};
    ssl_certificate /etc/letsencrypt/live/{auth}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{auth}/privkey.pem;
    server_tokens off;
    client_max_body_size 256k;
    if ($host != {auth}) {{ return 421; }}

    # Keep the Keycloak administrator interface private (e.g. VPN or SSH tunnel).
    # Block master-realm tokens and admin endpoints on the public staging hostname.
    location ^~ /admin/ {{ return 404; }}
    location = /admin {{ return 404; }}
    location ^~ /realms/master/ {{ return 404; }}
    location = /realms/master {{ return 404; }}
    location ^~ /metrics {{ return 404; }}
    location ^~ /health {{ return 404; }}

    location / {{
        proxy_pass http://127.0.0.1:18080;
        proxy_http_version 1.1;
        proxy_set_header Host {auth};
        proxy_set_header X-Forwarded-Host {auth};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Connection "";
        proxy_read_timeout 75s;
        proxy_cache off;
    }}
}}
"""


def write_once(output, content):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(content)


def main():
    parser = argparse.ArgumentParser(description="Generate two reviewed TLS-only staging vhosts")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name(".generated") / "staging-tls.conf")
    args = parser.parse_args()
    config = parse_env(args.env_file.read_text(encoding="utf-8"))
    source = render(config)
    write_once(args.output, source)
    print("Generated review-only staging TLS Nginx vhosts:", args.output)
    print("Certificate installation, DNS, nginx -t and reload are NOT performed.")


if __name__ == "__main__":
    main()
