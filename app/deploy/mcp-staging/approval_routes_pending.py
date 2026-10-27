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

# Review-only minimal *account bootstrap* surface. Never mix the draft-
# approval/write family into a task-read-only ChatGPT integration decision.
# The OAuth link endpoint remains gated by a verified external bearer and a
# one-use PRP-generated ticket; exposing a route does NOT solve ChatGPT's
# lack of user-visible bearer / invoke capability.
READONLY_LINK_EXACT = {
    path: EXACT[path] for path in (
        "/prp/login",
        "/prp/me/mcp-clients",
        "/api/auth/login",
        "/api/users/me",
        "/api/mcp/clients",
        "/api/mcp/clients/revoke",
        "/api/mcp/identity",
        "/api/mcp/identity/tickets",
        "/api/mcp/identity/unlink",
        "/api/mcp/link",
    )
}
# Review-only new first-party OIDC browser callback and PRP-authenticated
# PKCE start/finish APIs. Feature defaults off; separate G0 approval required.
READONLY_LINK_EXACT.update({
    "/prp/me/mcp-link/callback": "GET",
    "/api/mcp/identity/oidc/start": "POST",
    "/api/mcp/identity/oidc/finish": "POST",
})
READONLY_LINK_REGEX = {
    pattern: REGEX[pattern] for pattern in REGEX
    if pattern.startswith(r"^/prp/assets/")
}


def render_readonly_link_routes(trusted_ca, port=18443):
    """Generate narrower review-only link routes; NEVER installed by CI."""
    return _render_routes(trusted_ca, port, READONLY_LINK_EXACT, READONLY_LINK_REGEX)


def render_approval_routes(trusted_ca, port=18443):
    """Preserve the existing full review-only approval candidate unchanged."""
    return _render_routes(trusted_ca, port, EXACT, REGEX)


def _render_routes(trusted_ca, port, exact, regex):
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
    for path, verbs in exact.items():
        blocks.append("location = " + path + " {\n    limit_except " + verbs + " { deny all; }\n" + common + "}\n")
    # Quote regexes because canonical UUID quantifiers contain braces.
    for path, verbs in regex.items():
        blocks.append('location ~ "' + path + '" {\n    limit_except ' + verbs + ' { deny all; }\n' + common + '}\n')
    return "\n".join(blocks)
