"""Generate a review-only snippet. No install, reload or service operations.
Requires the separately reviewed MCP test server and its Origin/Host guards.
"""
import re

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
EXACT = {
    "/prp/login": "GET",
    "/prp/me/mcp-clients": "GET",
    "/api/auth/login": "POST",
    "/api/users/me": "GET",
    "/api/mcp/clients": "GET POST",
    "/api/mcp/clients/pairing": "POST",
    "/api/mcp/clients/revoke": "POST",
    "/api/mcp/identity": "GET",
    "/api/mcp/identity/tickets": "POST",
    "/api/mcp/identity/unlink": "POST",
    "/api/mcp/link": "POST",
}
REGEX = {
    r"^/prp/me/mcp-approve/" + UUID + "$": "GET",
    r"^/prp/assets/[A-Za-z0-9_-]+\.(js|css|woff2|woff|ttf|svg|png|webp|ico)$": "GET",
    r"^/api/mcp/approval/drafts/" + UUID + "$": "GET",
    r"^/api/mcp/approval/drafts/" + UUID + "/(approve|reject)$": "POST",
}

def render_approval_routes(trusted_ca, port=18443):
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("INVALID_LOOPBACK_PORT")
    if not re.fullmatch(r"/[A-Za-z0-9/_.-]+\.pem", trusted_ca) or "/../" in trusted_ca:
        raise ValueError("INVALID_REVIEWED_CA_PATH")
    common = """    if ($prp_stage_origin_ok = 0) { return 403; }
    client_max_body_size 8k;
    access_log off;
    proxy_pass https://127.0.0.1:%d;
    proxy_ssl_verify on;
    proxy_ssl_trusted_certificate %s;
    proxy_ssl_server_name on;
    proxy_ssl_name prp-test.micor.top;
    proxy_set_header Host prp-test.micor.top;
    proxy_set_header X-Forwarded-Host prp-test.micor.top;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Connection "";
    proxy_http_version 1.1;
    proxy_read_timeout 15s;
    proxy_buffering off;
    proxy_cache off;
    add_header Cache-Control "no-store" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header X-Content-Type-Options "nosniff" always;
""" % (port, trusted_ca)
    blocks = ["# PENDING REVIEW ONLY: do not include in live Nginx.\n"]
    for path, verbs in EXACT.items():
        blocks.append("location = " + path + " {\n    limit_except " + verbs + " { deny all; }\n" + common + "}\n")
    # Quote regexes because canonical UUID quantifiers contain braces.
    for path, verbs in REGEX.items():
        blocks.append('location ~ "' + path + '" {\n    limit_except ' + verbs + ' { deny all; }\n' + common + '}\n')
    return "\n".join(blocks)
