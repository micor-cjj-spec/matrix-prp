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


def render(template: str, legacy_approval: bool = False) -> str:
    anchor = "    location ^~ /.well-known/ { return 404; }"
    if template.count(anchor) != 1 or template.count("    location ^~ /api/mcp { return 404; }") != 1:
        raise ValueError("Expected the reviewed unified Staging deny-by-default template")
    blocks = []
    locations = [(f"= {path}", methods, maximum) for path, (methods, maximum) in ROUTES.items()]
    if legacy_approval:
        draft_id = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
        draft = f"^/api/mcp/approval/drafts/{draft_id}"
        locations.extend([
            (f'~ "{draft}$"', "GET", "8k"),
            (f'~ "{draft}/(?:approve|reject)$"', "POST", "8k"),
        ])
        # Allow only the anchored regexes above to override the MCP prefix deny.
        template = template.replace("location ^~ /api/mcp {", "location /api/mcp {", 1)
    for location, methods, maximum in locations:
        blocks.append(f"""    location {location} {{
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
    if sys.argv[1:] not in ([], ["--legacy-approval"]):
        raise SystemExit("Usage: render_mcp_readonly_gateway.py [--legacy-approval]")
    source = Path(__file__).with_name("nginx.conf.template").read_text(encoding="utf-8")
    sys.stdout.write(render(source, legacy_approval=bool(sys.argv[1:])))
