# Review-only human MCP approval routes

`approval_routes_pending.py` renders a snippet for separate review. It is not imported by any active Compose renderer or Nginx configuration. It does not install files, reload Nginx, change OAuth policies or enable MCP writes.

The snippet targets only `prp-test.micor.top`. It needs the existing reviewed Host/SNI/Authority and path canonicalization guards plus the `$prp_stage_origin_ok` map. It forwards to fixed loopback HTTPS, verifies the upstream chain and pins SNI to that host. The CA path and port are validated before rendering.

Pages are limited to login, MCP client grants, exact UUID draft approvals, and frontend assets.
The exact read-only browser-pairing workflow additionally uses
`POST /api/mcp/clients/pairing`, distinct from the generic owner client grant
and from `POST /api/mcp/link`. This *review-only* location is now explicitly
included; without it, the real CI pairing flow could pass behind a broad
disposable proxy while the separately allowlisted public staging UI would fail.
The location is POST-only and still requires backend owner reauthentication,
client checks, and the separate public-install transaction. No active
Nginx configuration references this snippet. APIs are restricted to the precise login/profile, grants, identity binding and draft-approval endpoints used by those pages. General `/prp/`, `/api/`, registration and administrator routes stay excluded. Write actions still require backend owner authentication, reauthentication and operation scopes. The UI keeps read-only scopes as its default.

Before any public installation, independently review this broader route surface, verify that the internal TLS gateway can serve these exact routes to the isolated backend, rebuild the frontend with `/prp/` and `/api`, and perform real browser login/grant/link/approval/revocation tests. Do not reuse the guard-only approval to authorize these extra routes. Public enabling requires a separate explicit decision.

Validation performed during development: five generator tests; seventeen actual isolated Nginx routing/TLS checks against a synthetic HTTPS upstream. These do not prove backend authentication, public reachability or real ChatGPT authorization. No production config was loaded.


## 2026-10-27 V2 first-party task-read route correction — still review-only

The older `render_approval_routes("/path/to/ca.pem")` intentionally retains
its **historical** broad approval-route candidate over the private
`https://127.0.0.1:18443` TLS ingress. That ingress currently generates
a `prp-test.micor.top` virtual host pointing at
`prp-mcp-stage-gateway-1:8080` in the **legacy** `18081` stack.
Do **not** reuse that broad candidate to enable a V2 first-party OAuth
browser login; it would risk crossing the two staging databases.

The **separate** `render_readonly_link_routes()` generator now targets
only `http://127.0.0.1:18082`, the operator-observed V2 gateway.
It refuses any alternate upstream, including `18081` and `18443`,
and does not require a CA file because both public Nginx and this
V2 upstream are on the same host loopback. The public HTTPS trust,
Host/SNI/Origin guards and verified outer TLS termination remain mandatory;
using loopback HTTP here does **not** downgrade public HTTPS.

Generate an inspectable (never installable by default) snippet via:

```sh
cd app/deploy/mcp-staging
python3 -B -c 'from approval_routes_pending import render_readonly_link_routes; print(render_readonly_link_routes())'
```

No service, database, Keycloak client, live Nginx file, B2 receipt or
production application is changed by this command. Even though the
candidate now points to V2, **do not install it**: the actual V2
gateway's SPA build, `/prp/me/mcp-link/callback` route and first-party
backend `/api/mcp/identity/oidc/start` and `finish` endpoints have
not been verified live. The Draft branch's browser code is not proof
it has been deployed to the older V2 service. Independent raw-URI
canonicalization checks, full G0/B2 authorization and recovery evidence
are still required. The existing PRP production and legacy stage
must stay unchanged.
