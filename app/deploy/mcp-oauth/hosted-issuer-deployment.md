# PRP MCP: hosted OAuth on a single 4C8G production server

Status: REVIEW ONLY — **not authorized for release**. The operator's
2026-10-21 read-only check found 1.3 GB available RAM and 40 GB free
disk, with PRP, Nginx and MySQL serving production at database V23.
Do not start Keycloak, PostgreSQL or a second MySQL on this host.

## Resource-efficient topology

ChatGPT/compatible client authenticates through a hosted OAuth provider.
The signed access token goes to the already existing PRP Java process's
/api/mcp endpoint. PRP validates the HTTPS JWKS, issuer, audience, signed
client, user association and owner-approved scope on each request.
Existing MySQL stores only V24–V26 draft/grant/identity tables. This
avoids **local** Keycloak/PostgreSQL resource consumption but requires
a trustworthy provider, operational reviews and measured Java capacity.

## Provider decision

1. **Hosted Auth0 is a candidate, not yet approved.** Its Resource
   Parameter Compatibility Profile must be enabled so the OAuth
   resource parameter selects the intended API audience. Configure
   the API identifier to equal the canonical public PRP MCP URL.
   Do not rely on Auth0's legacy audience parameter alone. Auth0's
   OIDC issuer commonly has a terminal slash; preserve it exactly.
   Signed tokens sometimes contain an additional /userinfo audience.
   PRP currently requires the exact MCP resource as one of the signed
   audiences, plus issuer, verified subject, client identity and
   PRP-side consent. Extra audiences must be explicitly risk-reviewed.
   Vendor billing, DCR support and terms are not yet confirmed.
2. **Do not assume another hosted IdP is interchangeable.** Current
   ZITADEL DCR docs state RFC 8707 resource may be ignored for
   audience narrowing. An issuer is not PRP-compatible until an
   actual PKCE token passes the configured MCP audience verification.
3. **Self-hosted Keycloak reference** passed full disposable CI PKCE,
   owner-link and MCP read/revocation tests; that does NOT justify
   permanently deploying Keycloak+PostgreSQL onto the current 4C8G.
4. **Building an authorization server inside PRP is deferred.**
   Implementing DCR/CIMD, user consent, PKCE, signing, rotation,
   refresh/revoke and auditing is a separate security-sensitive
   project, not a trivial RAM optimization.

## No-credential hosted issuer discovery gate

Run on a trusted machine or ephemeral CI runner:

    python3 app/deploy/mcp-oauth/hosted_issuer_gate.py \
      --issuer 'https://YOUR_TENANT.us.auth0.com/' \
      --resource 'https://micor.top/api/mcp' \
      --client-mode dcr

Use --client-mode cimd ONLY if discovery supports CIMD and an OpenAI-
compatible token authentication method. For a reviewed pre-registered
OAuth client use --client-mode provided --registered-client-id CLIENT_ID.
This tool does not register, log in, fetch tokens or change settings.
Passing discovery means **metadata_only, never production ready**.
CIMD, DCR and pre-registered OAuth client IDs must match the actual
ChatGPT connection's registration method and callbacks.

## Required independent live gates

- Provider admin must enable and verify RFC 8707 resource propagation
  in BOTH authorization and token requests. Check PKCE S256, real
  client registration, scope/consent policy, refresh/offline_access and
  token endpoint authentication method.
- Obtain a genuine test-user access token after Authorization Code +
  PKCE. Verify JWKS RSA signature, EXACT configured issuer and signed
  subject, audience containing canonical MCP URL, client_id/azp,
  granted task scope, expiration and rejection of wrong resource.
- Authenticate to PRP with a test account, password reauthenticate,
  authorize a known client, issue one-use link code, and test the
  bearer-only link endpoint, replay rejection, MCP read and immediate
  PRP-side grant revocation.
- Perform read-only capacity review on existing PRP heap/RSS, RAM,
  CPU, connections and disk at normal and peak loads. "No extra
  container" is not proof that existing JVM has adequate headroom.
- Production database currently V23: verify full backup restore,
  strictly additive migrations V24–V26 and all SSH/SFTP release
  controller and data-preservation gates. Never baseline or clean
  an existing populated database without approved recovery.
- Review production TLS, Host, Origin, rate limits, error logs
  (no secrets), provider outage behavior, JWKS rotation, credential
  lifecycle and revocation. Only then separately authorize read-only
  canary deployment with MCP write flag still OFF.

This document does NOT authorize any live OAuth tenant registration,
production migration, DNS/certificate changes, merge or deployment.

## References

RFC 8707: https://www.rfc-editor.org/rfc/rfc8707

OpenAI MCP OAuth: https://developers.openai.com/plugins/build/auth

Auth0 resource compatibility:
https://support.auth0.com/center/s/article/mcp-audience-error-with-auth0

ZITADEL DCR resource limitations:
https://zitadel.com/docs/guides/integrate/dynamic-client-registration

OpenAI MCP entitlement / refresh requirements:
https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
