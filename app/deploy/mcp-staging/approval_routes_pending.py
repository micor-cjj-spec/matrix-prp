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
    r"^/prp/assets/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.(js|css|woff2|woff|ttf|svg|png|webp|ico)$": "GET",
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
    # Referenced by the built Vue HTML or registered on secure startup.
    # Expose only exact GETs, never a generic /prp/** or broad API proxy.
    "/prp/favicon.svg": "GET",
    "/prp/icon.svg": "GET",
    "/prp/manifest.webmanifest": "GET",
    "/prp/sw.js": "GET",
})
READONLY_LINK_REGEX = {
    pattern: REGEX[pattern] for pattern in REGEX
    if pattern.startswith(r"^/prp/assets/")
}


def render_readonly_link_routes(port=18082):
    """V2-only minimal browser/link routes, review ONLY, never installed.

    18443 is NOT a V2 upstream: its prp-test vhost currently forwards to
    the older 18081 stage and its separate database. Route directly to the
    explicitly observed 18082 V2 HTTP loopback gateway; the outer reviewed
    public Nginx TLS vhost terminates HTTPS. Not a deployment authorization.
    """
    if type(port) is not int or port != 18082:
        raise ValueError("V2_READONLY_ROUTES_REQUIRE_EXACT_18082")
    return _render_routes(None, port, READONLY_LINK_EXACT,
                          READONLY_LINK_REGEX, tls_upstream=False)


def render_approval_routes(trusted_ca, port=18443):
    """Preserve the earlier full approval/write-family review artifact."""
    return _render_routes(trusted_ca, port, EXACT, REGEX, tls_upstream=True)


def _render_routes(trusted_ca, port, exact, regex, *, tls_upstream):
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise ValueError("INVALID_LOOPBACK_PORT")
    if tls_upstream:
        if not isinstance(trusted_ca, str) or not re.fullmatch(
                r"/[A-Za-z0-9/_.-]+\.pem", trusted_ca) or "/../" in trusted_ca:
            raise ValueError("INVALID_REVIEWED_CA_PATH")
        upstream = (
            "    proxy_pass https://127.0.0.1:%d;\n"
            "    proxy_ssl_verify on;\n"
            "    proxy_ssl_trusted_certificate %s;\n"
            "    proxy_ssl_server_name on;\n"
            "    proxy_ssl_name prp-test.micor.top;\n"
        ) % (port, trusted_ca)
    else:
        if port != 18082 or trusted_ca is not None:
            raise ValueError("V2_REVIEW_LOOPBACK_UPSTREAM_MISMATCH")
        upstream = "    proxy_pass http://127.0.0.1:18082;\n"
    common = ("""    if ($prp_stage_origin_ok = 0) { return 403; }
    client_max_body_size 8k;
    access_log off;
""" + upstream + """    proxy_set_header Host prp-test.micor.top;
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
""")
    blocks = ["# PENDING REVIEW ONLY: do not include in live Nginx.\n"]
    for path, verbs in exact.items():
        # Nginx matches normalized $uri. This must also validate the
        # ORIGINAL request target, otherwise percent-encoded aliases can
        # reach an exact location. The optional query is required by the
        # OAuth callback (code/state/iss); only the PATH is pinned here.
        canonical = ""
        if not tls_upstream:
            pattern = "^" + re.escape(path) + r"(?:\?.*)?$"
            # Nginx's limit_except GET *also permits HEAD*. Enforce the
            # actual method against the exact reviewed verb set here.
            allowed_methods = "|".join(verbs.split())
            canonical = ('    if ($request_uri !~ "' + pattern
                         + '") { return 404; }\n'
                         + '    if ($request_method !~ "^(?:'
                         + allowed_methods + ')$") { return 405; }\n')
        blocks.append("location = " + path + " {\n    limit_except " + verbs
                      + " { deny all; }\n" + canonical + common + "}\n")
    # Quote regexes because canonical UUID quantifiers contain braces.
    for path, verbs in regex.items():
        canonical = ""
        if not tls_upstream:
            # The raw, undecoded URL has the same single-segment asset
            # grammar. A normalized, encoded or path-aliased URL must fail.
            pattern = path[:-1] + r"(?:\?.*)?$"
            allowed_methods = "|".join(verbs.split())
            canonical = ('    if ($request_uri !~ "' + pattern
                         + '") { return 404; }\n'
                         + '    if ($request_method !~ "^(?:'
                         + allowed_methods + ')$") { return 405; }\n')
        blocks.append('location ~ "' + path + '" {\n    limit_except '
                      + verbs + ' { deny all; }\n' + canonical
                      + common + '}\n')
    return "\n".join(blocks)
