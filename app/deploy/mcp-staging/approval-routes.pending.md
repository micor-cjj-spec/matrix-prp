# Review-only human MCP approval routes

`approval_routes_pending.py` renders a snippet for separate review. It is not imported by any active Compose renderer or Nginx configuration. It does not install files, reload Nginx, change OAuth policies or enable MCP writes.

The snippet targets only `prp-test.micor.top`. It needs the existing reviewed Host/SNI/Authority and path canonicalization guards plus the `$prp_stage_origin_ok` map. It forwards to fixed loopback HTTPS, verifies the upstream chain and pins SNI to that host. The CA path and port are validated before rendering.

Pages are limited to login, MCP client grants, exact UUID draft approvals, and frontend assets. APIs are restricted to the precise login/profile, grants, identity binding and draft-approval endpoints used by those pages. General `/prp/`, `/api/`, registration and administrator routes stay excluded. Write actions still require backend owner authentication, reauthentication and operation scopes. The UI keeps read-only scopes as its default.

Before any public installation, independently review this broader route surface, verify that the internal TLS gateway can serve these exact routes to the isolated backend, rebuild the frontend with `/prp/` and `/api`, and perform real browser login/grant/link/approval/revocation tests. Do not reuse the guard-only approval to authorize these extra routes. Public enabling requires a separate explicit decision.

Validation performed during development: five generator tests; seventeen actual isolated Nginx routing/TLS checks against a synthetic HTTPS upstream. These do not prove backend authentication, public reachability or real ChatGPT authorization. No production config was loaded.
