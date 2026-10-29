# ChatGPT OAuth exact-client pre-registration: deployment review (NO-GO)

## Verified staging evidence (2026-10-29)
- Keycloak 26.8.0, `kc.features=cimd,resource-indicators`, hostname `https://auth-test.micor.top`.
- Realm `prp-mcp`: PostgreSQL read-only count for `client_id='https://chatgpt.com/oauth/client.json'` = **0**; Realm has **13** clients.
- Keycloak logs for the exact ID: `error="client_not_found"`.
- MCP unauthenticated POST returns 401 Bearer resource metadata; protected resource metadata and OIDC discovery return 200.
- `app/deploy/mcp-oauth/ci_chatgpt_cimd_pkce.py` proves exact pre-registration in disposable Keycloak 26.8.0/26.8.1 CI, **not** on staging.
- Native CIMD parser in tested Keycloak versions rejects the official ChatGPT metadata field `token_endpoint_auth_methods_supported`; the exact-client alternative was tested only with isolated CI keys, not a real ChatGPT assertion.
- `prp-mcp-oauth-stage-cimd-egress-1` is exited (137); its relationship to any future policy change must be reviewed.
- B2 evidence inventory: `deployment_permitted=false`; approved install and fresh B2 restore receipts missing.

## Intended change (review only)
- **Never** use `start --import-realm`, SQL writes, or blanket Realm export/import to add a client.
- Use scoped Keycloak Admin API only after authorization and fresh restoration evidence are independently verified.
- Register **one** exact client ID `https://chatgpt.com/oauth/client.json`, redirect `https://chatgpt.com/connector_platform_oauth_redirect`, official `https://chatgpt.com/oauth/jwks.json`, confidential `client-jwt`, authorization code, S256, consent required, fullScopeAllowed=false, default `basic`, optional `prp.tasks.read` and `offline_access`, explicit MCP audience `https://prp-test.micor.top/api/mcp`.
- Review actual Realm policies/profiles via authenticated Admin API before any policy edit; never disable unrelated policies. CI policy name `ci-chatgpt-cimd-only` is disposable-test-specific and must not be assumed to exist in staging.
- Check current client count and exact-ID absence immediately before registration. Stop on any discrepancy; no automatic overwrite.
- Treat refresh/rotation/revocation, external TLS, real ChatGPT private-key JWT, and `prp_tasks_list` as **unverified live acceptance checks**.

## Preconditions / stop conditions
1. Independent B2 reviewer approves exact change and scope, with a documented operator and maintenance window.
2. Fresh B2 restore evidence and rollback feasibility are verified; historical snapshot metadata is insufficient.
3. Capture a safe, secret-free inventory of the 13 existing clients and client policies, and compare before/after.
4. Prove official JWKS reachability from Keycloak's runtime path, external TLS verification without `-k`, and unchanged issuer/resource metadata.
5. Review potential effect of disabled CIMD egress container; avoid incidental changes.
6. No existing exact ID, unexpected policy, invalid backup, or failed preflight: **STOP**.

## Controlled implementation sequence (NOT AUTHORIZED HERE)
- Read-only Admin API snapshot: exact client ID, 13 client identifiers, client policies/profiles and scope availability.
- Apply only the exact new client via Admin API; no existing client update, no global policy replacement.
- Re-read exact representation, optional scopes, redirect, JWKS, S256, audience; compare other client inventory unchanged.
- Perform real ChatGPT OAuth login/consent/code/token validation and least-privilege `prp_tasks_list` acceptance.
- Roll back only the newly created client **if and only if** the created internal ID is independently verified and rollback authorized; do not delete on ID collision.

## Out of scope
Production migration, MySQL/Flyway changes, Nginx reload, Keycloak restart, encrypted export, new server, approval fabrication.

**Status: NO-GO. This file is documentation only; committing it does not authorize or execute deployment.**
