# ChatGPT ↔ PRP MCP: live connection gate review (NO-GO)

Status: **REVIEW ONLY**. This is not an installation procedure, approval, or release receipt. Do not change production Keycloak, Nginx, databases, or OAuth clients until the independent B2 gate is satisfied.

## Observed baseline (historical, must be rechecked)
- Live Keycloak 26.8.0 inventory previously showed 13 clients, with **zero** exact `https://chatgpt.com/oauth/client.json` clients. The observed authorization failure was `client_not_found`.
- Proposed issuer: `https://auth-test.micor.top/realms/prp-mcp`; resource: `https://prp-test.micor.top/api/mcp`. Historical public DNS/routing evidence is incomplete or conflicting. These values are **candidates**, not verified publicly reachable endpoints.
- ChatGPT exact client ID: `https://chatgpt.com/oauth/client.json`; redirect: `https://chatgpt.com/connector_platform_oauth_redirect`.
- First-party identity-link client `prp-first-party-link` and callback `https://prp-test.micor.top/prp/me/mcp-link/callback` are separate requirements.

## What CI actually proves
- [Run 40988463663](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40988463663): Keycloak 26.8.0/26.8.1 accepted a **synthetic** inline-JWKS `private_key_jwt` with S256 authorization code, consent, task-only audience/scope, refresh rotation/replay/revocation. The inline key was substituted **only in disposable CI**.
- [Run 40989064826](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40989064826): both versions rejected unknown `kid` and incorrect JWT `aud`.
- [Run 40991522516](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40991522516): both versions passed mocked missing/stopped/wrong-name/wrong-image/missing-label disposable-container guard negatives.
- Official public JWKS reachability from a helper container sharing the Keycloak network namespace **does not** prove the Keycloak JVM fetched it or accepted a real ChatGPT assertion.

## Independent blockers (all must be resolved before claiming connection)

| Gate | Evidence required | Current status |
|---|---|---|
| B2 recoverability | Independently reviewed backup, restore test, rollback proof, authorization | **NO-GO** |
| Public HTTPS/DNS | External resolution, trusted certificate, reverse-proxy paths, resource and issuer reachability | **UNVERIFIED** |
| OAuth metadata | Live `/.well-known/oauth-protected-resource`, issuer discovery, exact `authorization_servers`, PKCE S256 and supported scopes | **UNVERIFIED LIVE** |
| Exact client | Approved create-only registration of exact ChatGPT client; redirect, consent, `client-jwt`, `fullScopeAllowed=false`, least privilege | **ABSENT IN HISTORICAL INVENTORY** |
| Client policies | Explicitly review native CIMD interception, profiles, policies and Keycloak URL-JWKS retrieval; do not silently disable policies | **UNVERIFIED LIVE** |
| Real signer | Real ChatGPT `private_key_jwt` signed with a public-key match from official JWKS accepted by live Keycloak; no test private key | **NOT TESTED** |
| First-party identity | Registered first-party client, reachable callback, same Realm subject, owner mapping | **UNVERIFIED** |
| Real MCP operation | User-authorized ChatGPT connector completes login/consent and reads up to 20 owner `prp_tasks_list` records; finance/wellness/writes denied | **NOT TESTED** |

## Decision sequence (no live mutations in this PR)
1. Collect **read-only** current public DNS/TLS/HTTP metadata and live Keycloak inventory; classify discrepancies without printing secrets or tokens.
2. Independently complete B2 restore/rollback evidence and obtain explicit approval for any client or policy mutation.
3. Review create-only client registration and policy interactions against **current** live realm state; do not transplant synthetic inline JWKS, test credentials, or CI overrides.
4. Only in a separately approved change window, register exact clients and validate a **real** ChatGPT-signed assertion and full connector callback.
5. Verify subject binding and task-read-only MCP operation; retain denial tests and rollback evidence. Do not mark connected until this step passes.

**Decision: CI compatibility PASS; real ChatGPT connection UNVERIFIED; B2 NO-GO.**
