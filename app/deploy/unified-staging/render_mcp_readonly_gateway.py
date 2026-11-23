"""Render a review-only task-read gateway without changing the baseline template."""
import sys
from pathlib import Path

ROUTES = {
    "/.well-known/oauth-protected-resource/api/mcp": ("GET", "8k"),
    "/api/mcp": ("POST", "128k"),
    "/api/mcp/clients": ("GET POST", "8k"),
    "/api/mcp/clients/revoke": ("POST", "8k"),
    "/api/mcp/identity": ("GET", "8k"),
    "/api/mcp/identity/unlink": ("POST", "8k"),
    "/api/mcp/identity/oidc/start": ("POST", "8k"),
    "/api/mcp/identity/oidc/finish": ("POST", "8k"),
}


def render(template: str) -> str:
    anchor = "    location ^~ /.well-known/ { return 404; }"
    if template.count(anchor) != 1 or template.count("    location ^~ /api/mcp { return 404; }") != 1:
        raise ValueError("Expected the reviewed unified Staging deny-by-default template")
    blocks = []
    for path, (methods, maximum) in ROUTES.items():
        blocks.append(f"""    location = {path} {{
        limit_except {methods} {{ deny all; }}
        client_max_body_size {maximum};
        proxy_pass http://backend:8080;
        proxy_http_version 1.1;
        proxy_set_header Host ${{PRP_STAGE_HOST}};
        proxy_set_header X-Forwarded-Host ${{PRP_STAGE_HOST}};
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        add_header Cache-Control "no-store" always;
    }}""")
    return template.replace(anchor, "\n\n".join(blocks) + "\n\n" + anchor)


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: render_mcp_readonly_gateway.py > reviewed-gateway.conf.template")
    source = Path(__file__).with_name("nginx.conf.template").read_text(encoding="utf-8")
    sys.stdout.write(render(source))

