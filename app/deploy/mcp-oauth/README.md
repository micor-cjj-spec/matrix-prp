# Isolated reference OAuth authorization server for PRP MCP

This folder provides an **opt-in reference deployment**, not an installed or enabled production component.
Uses Keycloak 26.8.0 (separate PostgreSQL, not PRP's MySQL) with RFC 8414 authorization metadata.
MCP CIMD and resource indicators in Keycloak are **experimental**; do not treat this stack as production-approved without version-specific validation.

## Prerequisites and trust boundaries

1. Reserve an HTTPS authorization hostname such as `https://auth.example.org` and arrange TLS/DNS outside this repository. Configure a locked-down reverse proxy to `127.0.0.1:18080`; never expose the Keycloak port or PostgreSQL port directly on the Internet. Set trustworthy Host, X-Forwarded-Proto/For/Host headers in your proxy and reject unexpected Host names.
2. Provision separate high-entropy Keycloak database/admin credentials in a private local `.env` file. This repo contains only `.env.example`, never real secrets or tokens. Protect persistent PostgreSQL data and plan backup/restore, patching, login hardening and key rotation.
3. Review Keycloak experimental features: `cimd` and `resource-indicators`. The included realm contains **no clients or users**; operator registration, scope policies and consent are still required.
4. Only for an **isolated staging system**, execute `docker compose --env-file .env -f compose.yaml config`; after reviewing output, `docker compose --env-file .env -f compose.yaml up -d`. This is not a request to run these commands on production.
5. Open Keycloak Admin and verify `prp-mcp` realm under the issuer hostname. Verify that the issuer matches `https://auth.example.org/realms/prp-mcp` **exactly** and contains the expected `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and `S256` PKCE support.
6. Configure one explicitly trusted **OAuth public client** with Authorization Code + PKCE/S256 and exact HTTPS/localhost redirect URIs; no wildcards. Review OpenAI/other client's supported CIMD/registration metadata. Do not enable unrestricted dynamic client registration. Restrict resource indicators and audiences to the **actual, canonical PRP MCP URL**, not a guessed path.
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
