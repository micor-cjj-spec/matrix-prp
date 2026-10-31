# ChatGPT ↔ PRP MCP OAuth acceptance matrix (review-only)

**Status: NO-GO.** This is a test specification, not authorization to register a client or modify an existing Keycloak Realm. No secrets or real tokens should be committed.

## Proven vs unproven

| Gate | Current evidence | Acceptance requirement | Status |
|---|---|---|---|
| Isolated PostgreSQL restore | Original custom dump restored, realm `prp-mcp` and 13 clients | Restored DB usable by matching Keycloak image | PASS (operator evidence) |
| Isolated Keycloak application startup | Keycloak 26.8.0 boot and OIDC discovery HTTP 200 | Discovery contains issuer, authorization and token endpoints | PASS (operator evidence) |
| Isolated cleanup | Guarded removal of temporary KC, DB, network | Original dump hash unchanged | PASS (operator evidence) |
| Live OAuth client registration | Exact client absent, `client_not_found` | Approved scoped registration, no existing-client drift | BLOCKED |
| Live ChatGPT JWT client authentication | Disposable CI keys only | Actual ChatGPT-signed assertion verified against official JWKS | NOT TESTED |
| OAuth code + PKCE | Disposable CI harness only | Real ChatGPT callback/code exchange, PKCE S256 | NOT TESTED |
| Access token validation | Metadata endpoints available | Issuer, audience, signature, expiry, scopes, resource binding verified | NOT TESTED |
| MCP tool call | No real successful call | `prp_tasks_list` returns only authorized user's tasks | NOT TESTED |
| Refresh, rotation, revocation | No live evidence | Refresh and revocation behavior validated without secret disclosure | NOT TESTED |
| Independent B2 authorization | Missing signed acceptance and install receipts | Independent reviewer + scoped change authorization | BLOCKED |

## Read-only pre-change checks (only after independent authorization to proceed)

1. Capture live issuer, protected-resource metadata, `authorization_servers`, token endpoint authentication methods, and supported scopes; compare expected resource `https://prp-test.micor.top/api/mcp`.
2. Read Keycloak Realm client list and policy/profile inventory with an authorized read-only identity; verify exact client ID `https://chatgpt.com/oauth/client.json` is absent. Stop if counts or identities drift from the reviewed baseline.
3. Confirm official ChatGPT metadata and JWKS are reachable from the **actual Keycloak runtime network**; check certificate verification and the currently published algorithm/key requirements. Do not use the disposable CI signing key for real-client acceptance.
4. Confirm actual Keycloak support for confidential `client-jwt`, consent, PKCE S256, redirect URI, scope mappings and audience mapper. No global Realm policy changes.
5. Confirm approved rollback plan is limited to the newly created, independently verified client internal ID. Never delete by display name or a guessed ID.

## Post-change acceptance (requires separate approved change)

- Real browser authorization: verify correct issuer, consent, redirect and code callback; do not paste codes or tokens into issues.
- Token endpoint: verify actual client assertion and code verifier; confirm token signature, `iss`, `aud`, `exp`, and least-privilege scopes.
- MCP: verify an authenticated `prp_tasks_list` and a negative test for unauthorized scope/resource. Avoid exposing personal task contents in CI logs.
- Negative tests: unknown client, wrong redirect, missing PKCE, wrong audience, expired assertion, invalid scope and revoked refresh token must fail closed.
- Audit: compare original 13 client IDs and policies before/after; any unexpected drift triggers rollback review.
- Record sanitized pass/fail, reviewer, change window, rollback outcome, and final disposition in an independently approved artifact.

## Stop rules

Any absent approval, missing fresh restore receipt, metadata mismatch, untrusted TLS, JWKS unreachability, unexpected Realm policy, client ID collision or existing-client drift means **STOP**. No automated deployment, Nginx reload, Keycloak restart, production database operation, or approval fabrication is permitted.

References: `CHATGPT_PREREG_DEPLOY_REVIEW.md`, `B2_APP_RESTORE_EVIDENCE_20261030.md`, `B2_APP_RESTORE_CLEANUP_20261030.md`.
