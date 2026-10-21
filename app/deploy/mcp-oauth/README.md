# Isolated reference OAuth authorization server for PRP MCP

This folder provides an **opt-in reference deployment**, not an installed or enabled production component.
Uses Keycloak 26.8.0 (separate PostgreSQL, not PRP's MySQL) with RFC 8414 authorization metadata.
MCP CIMD and resource indicators in Keycloak are **experimental**; do not treat this stack as production-approved without version-specific validation.

## Prerequisites and trust boundaries

1. Reserve an HTTPS authorization hostname such as `https://auth.example.org` and arrange TLS/DNS outside this repository. Configure a locked-down reverse proxy to `127.0.0.1:18080`; never expose the Keycloak port or PostgreSQL port directly on the Internet. Set trustworthy Host, X-Forwarded-Proto/For/Host headers in your proxy and reject unexpected Host names.
2. Provision separate high-entropy Keycloak database/admin credentials in a private local `.env` file. This repo contains only `.env.example`, never real secrets or tokens. Protect persistent PostgreSQL data and plan backup/restore, patching, login hardening and key rotation.
3. Review Keycloak experimental features: `cimd` and `resource-indicators`. The included realm contains **no clients or users**; operator registration, scope policies and consent are still required.
4. Before staging start, generate the **exact protected-resource client URI**. Keycloak `resource-indicators` requires a registered MCP resource URI (`resource_url` client attribute) or it may return `invalid_target` during Authorization Code + PKCE. Use a canonical URI equal to the PRP OAuth `resource`, after verifying the actual Nginx proxy path. For example:
   ```bash
   cd app/deploy/mcp-oauth
   python3 build_realm.py --resource https://prp.staging.example.org/api/mcp
   docker compose --env-file .env -f compose.yaml config
   ```
   This produces `.generated/realm/prp-mcp-realm.json` with exactly one **bearer-only** resource server client and no login clients. Review it and the Compose output; then, only on an isolated staging system, run `docker compose --env-file .env -f compose.yaml up -d`. Do **not** launch this on PRP production. The generated realm is **first-import only**; `--import-realm` does not rewrite an existing Keycloak realm. Never overwrite stateful realms without a reviewed migration.
5. Open Keycloak Admin and verify `prp-mcp` realm under the issuer hostname. Verify that the issuer matches `https://auth.example.org/realms/prp-mcp` **exactly** and contains the expected `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and `S256` PKCE support.
6. Configure one explicitly trusted **OAuth public client** with Authorization Code + PKCE/S256 and exact HTTPS/localhost redirect URIs; no wildcards. In Keycloak, assign an **Audience** mapper on that client whose Included Client Audience is `matrix-prp-mcp-resource` (or use the approved CIMD resource indicator policy). Verify the resulting access-token `aud` is the exact `resource_url` and that OAuth access tokens present signed `azp` or matching `client_id` for the requesting client. Review OpenAI/other client's supported CIMD/registration metadata. Do not enable unrestricted dynamic client registration. Restrict resource indicators and audiences to the **actual, canonical PRP MCP URL**, not a guessed path.
7. Assign signed `client_id` (or explicitly configure the corresponding mapper; PRP currently validates signed `client_id`), and the exact requested PRP scope claims. **No `prp_user_id` claim should be used for account authorization.** Instead, the user must link verified Keycloak issuer+subject to their PRP account via V26.
8. PRP owner uses `我的 → MCP 客户端授权` to approve the signed `client_id` and selected scopes, verify their PRP password, and generate a 10-minute one-use linking code.
9. OAuth bearer and linking code are exchanged **only with the OAuth-protected** `POST /api/mcp/link` endpoint via a trusted compatible client:
   ```http
   POST /api/mcp/link
   Authorization: Bearer <validated external OAuth access token>
   Content-Type: application/json

   {"ticket":"<the one-time linking code>"}
   ```
   The user must **not** send Keycloak credentials, bearer tokens or pairing codes to a general ChatGPT prompt. This is an operator bootstrap route, not a chat tool. It only accepts signed bearer from the configured OAuth issuer and enforces signed `client_id` against the PRP ticket/grant.
10. After linking, authenticated MCP `initialize → tools/list → tools/call` is expected to work with exactly the intersection of provider-granted scopes and PRP owner-approved scopes; PRP password-based draft review is still required for actual business writes.

## Actual PRP public routing — do not confuse /prp/ with /api/

Existing PRP deployment documentation (`app/docs/technical/prp-subpath-deployment.md`) confirms that:
- Vue Web/PWA is served under `https://micor.top/prp/`.
- Spring Boot is accessible through **`/api/**`**, proxying unchanged to the Java service on `127.0.0.1:11000`.
- Thus a same-host public MCP endpoint is **`https://micor.top/api/mcp`**, not `https://micor.top/prp/api/mcp`; the public RFC 9728 discovery path is `/.well-known/oauth-protected-resource/api/mcp`.

For a separately isolated staging hostname (preferred) generate an **Nginx review snippet** before configuring the actual TLS server block:

```bash
cd app/deploy/mcp-oauth
python3 render_nginx.py --host mcp.staging.example.org --output .generated/mcp-routes.conf
```

Review the generated exact locations for `/api/mcp`, `/api/mcp/link`, and the OAuth discovery URI. Insert them **only in an existing, trusted HTTPS `server_name mcp.staging.example.org` block**, alongside a catch-all default server that rejects unexpected Host values. Set a valid TLS certificate and preserve existing PRP `/api/` routes. Run `sudo nginx -t` before reload. **Do not add `/prp/` to the backend API routes or change production Nginx automatically.**

The snippet pins upstream Host, forwarded host/proto, and disables proxy buffering for the streaming MCP path; the Java backend still authenticates every MCP request independently. Do not forward arbitrary user-supplied `X-Forwarded-Host` values. Rate limits, logging redaction, request body limits, resource exhaustion protection, header policies, and origin controls require operator review at the TLS gateway. The snippet does not create an Nginx server or certificate.

Once the staging MCP feature and OAuth issuer are deliberately enabled, run an **unauthenticated, no-secrets, read-only** public routing test from an external machine:

```bash
cd app/deploy/mcp-oauth
python3 public_route_preflight.py \
  --resource https://mcp.staging.example.org/api/mcp \
  --issuer https://auth.staging.example.org/realms/prp-mcp
```

This validates public protected-resource metadata, exact canonical audience and external issuer, and that an **unauthenticated MCP initialize returns HTTP 401** with the exact `WWW-Authenticate: Bearer resource_metadata="..."` challenge. It explicitly rejects PRP's production `micor.top` host and won't log user data or submit writes. A passing result does **not** prove Keycloak login, approved PRP account linkage or live tool execution; those require the separate PKCE smoke below.

## Controlled authorization-code + PKCE + MCP round-trip

This is a **manual workstation test for an isolated staging environment**. It is not run by CI because it requires a human to sign into the external Keycloak account and approve scopes.

1. Create a private DNS/TLS-backed staging Keycloak and MCP resource. Verify the actual public MCP URL (it may differ from PRP's internal `/api/mcp` route). Register that exact URL using `resource_url`. The staging resource, OAuth audience, PRP `MATRIX_PRP_MCP_OAUTH_RESOURCE` and the OAuth `resource` request parameter must match exactly.
2. Before the **first Keycloak realm import**, generate one extra **read-only** local-browser PKCE client; for example:
   ```bash
   cd app/deploy/mcp-oauth
   python3 build_realm.py \
     --resource https://prp.staging.example.org/api/mcp \
     --staging-client-id prp-pkce-probe \
     --staging-redirect http://127.0.0.1:8765/callback
   ```
   It has exact loopback redirect, explicit S256 PKCE, consent required, a single optional `prp.tasks.read` scope and an MCP Resource Audience mapper. No finance/read or write scopes are granted by default.
3. Start only the staging Keycloak stack using the reviewed Compose workflow, and create a **test identity** (username/password) in the staging realm using Keycloak Admin. Verify the Keycloak login UI and that Keycloak acknowledges the read-only scope and `resource` parameter. For real ChatGPT clients, registration/CIMD policy and exact ChatGPT callback URIs must be reviewed separately; this local test client is not ChatGPT.
4. Use the staging PRP `我的 → MCP 客户端授权` interface. Re-enter the PRP password, authorize `prp-pkce-probe` with only `prp.tasks.read`, then issue a one-time OAuth identity-linking code. Do **not** send it through a normal AI chat or commit it to Git.
5. On your **own local machine with a browser** (not on a remote headless server), execute:
   ```bash
   cd app/deploy/mcp-oauth
   python3 pkce_smoke.py \
     --issuer https://auth.staging.example.org/realms/prp-mcp \
     --resource https://prp.staging.example.org/api/mcp \
     --client-id prp-pkce-probe \
     --redirect-uri http://127.0.0.1:8765/callback
   ```
   Follow the printed authorization URL in your **local browser**. The script checks `state`, optional `iss`, uses `code_verifier` and the identical OAuth `resource` for token exchange, requests the linking code through a hidden terminal prompt, and invokes PRP's bearer-only linking endpoint. It then exercises MCP initialization, tools/list and a **read-only** task tool invocation. Its success output contains no bearer, linkage code or task contents.
6. If the account was already linked and you are re-testing, add `--already-linked` to skip issuing a new PRP linking code.

Prerequisites: Python 3.11+, ability to open a local browser with loopback redirect, a genuine external OAuth issuer reachable via TLS, and an isolated PRP backend with OAuth enabled and an owner-approved client. **Never run the script with production access tokens or private user data as a first test.** It performs real read-only requests and a one-time account link when requested, not database migrations or deployment.

Read-only automated CI exercises the script's PKCE/state/issuer/audience construction and the fact it does not print tokens or private task contents. Passing these tests does not prove the live Keycloak deployment or ChatGPT connection. A real PKCE sign-in and positive/negative token exchange must be manually verified in the staging environment before deployment.

## Metadata preflight

From a trusted shell with Python 3.11+, run:

```bash
python3 app/deploy/mcp-oauth/check_metadata.py \
  --issuer https://auth.example.org/realms/prp-mcp \
  --resource https://your-prp.example.org/api/mcp
```

The script only reads public OIDC/OAuth discovery and JWKS, checks issuer consistency, required endpoints, an RS256 signing key and PKCE S256; it never enrolls a client, logs in or obtains tokens. Do not mistake metadata preflight success for complete signed-token or live end-to-end verification.

## Release blockers

This reference deployment is **not** the PRP production OAuth deployment. Before activation, review the current PRP public API rewrite path, host/origin protections, issuer and audience, external provider key rotation, OAuth client registration/CIMD security policy, `resource` propagation, high availability/backups, request-rate limits, user linking UX, production logs, and PRP release preservation/SSH gates. Enable `MATRIX_PRP_MCP_ENABLED`, `MATRIX_PRP_MCP_OAUTH_ENABLED`, `MATRIX_PRP_MCP_WRITE_ENABLED` only following distinct staged acceptance.

Official references: Keycloak MCP integration guide and OpenAI Plugin OAuth guidance.
