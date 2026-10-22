# PRP MCP Gateway · P0 (2026-10)

## Scope

Introduce an opt-in Spring AI 1.1.8 MCP **stateless Streamable HTTP** endpoint in the existing Boot 3.5.3 / Java 21 backend.
It reuses owner-scoped PRP services instead of granting the model SQL access or a database login.

- `prp_tasks_list` — maximum 20 authenticated-user tasks.
- `prp_finance_month` — summary and maximum 10 transactions for an authenticated user's selected month.
- `prp_wellness_daily` — authenticated-user daily wellness data.
- `prp_prepare_task`, `prp_prepare_finance`, `prp_prepare_record` — save an immutable 15-minute draft, **not** business data.
- `prp_draft_status` — owner-scoped read of current status.
- `prp_confirm_draft` — only works **after** the PRP site verifies the account password and marks this exact draft `APPROVED`; locks the draft, writes one business record and returns the same saved result on replay. No model-supplied approval flag, delete or update tools.

A model cannot supply user IDs, SQL, file paths, destination URLs, or arbitrary method names. JWT authentication is supplied by the existing servlet security chain; CurrentUser.id() is resolved at execution time and never copied from a tool argument. Cross-user draft IDs return 404.

## Flags (default **OFF**)

```properties
MATRIX_PRP_MCP_ENABLED=false
MATRIX_PRP_MCP_WRITE_ENABLED=false
```

When MCP is enabled, the endpoint is `/api/mcp` on the app's private HTTP origin. The public Nginx prefix, if any, is an infrastructure concern; do not add a public proxy until security acceptance. The implementation uses Spring AI's `spring-ai-starter-mcp-server-webmvc` with `spring.ai.mcp.server.protocol=STATELESS`. The scanner picks up only the explicit PRP MCP-annotated methods; automatic conversion of other Spring AI ToolCallbacks to MCP tools is disabled.

This **does not** implement third-party OAuth 2.0. Existing PRP JWT authentication is useful for private MCP Inspector/compatible-client smoke tests, but it is **not** sufficient for ChatGPT remote MCP app OAuth onboarding. JWTs expire, and there is no client-registration, discovery or token refresh flow. Do not claim that ChatGPT Plus can write through this gateway.

## Database & release policy

The production branch already owns `V24__vocal_song_library_and_assignments.sql`. To avoid irreversible Flyway version collision, MCP migrations are now **V25 drafts, V26 client grants, V27 identity links**. See `mcp-flyway-lineage-reconciliation.md`. This version renumbering is compatible with **fresh** schemas only: the previously validated staging DB retains the legacy V24–V26 history and must not be auto-upgraded or silently repaired.


V25 introduces only an initially-empty `prp_mcp_write_drafts` table, including `approval_failures` (five-attempt lockout), `approved_at` and `CONSUMED` replay receipts. It is registered with a SHA-256 in the reviewed additive migration policy. V1–V24 (including the production vocal V24) remain untouched; deploy **in order** on a reviewed restored copy. Do not baseline or clean the production schema, truncate any user data, bypass snapshot/diff gates, or run Flyway on a populated environment without a reviewed baseline.

No production deployment is part of this PR. In particular, the current SSH/SFTP/release-gateway hold must remain in place until separately accepted.

## Security invariants

1. Endpoint **disabled by default**; no unauthenticated MCP access.
2. Existing JWT filter binds each request to an enabled PRP user. Business service methods enforce owner-scoped reads/writes.
3. Fail closed if MCP invocation executes without a propagated Spring Security principal. Test **real HTTP transport** and streaming/non-streaming context propagation before enabling remotely.
4. Reads are bounded; writes are disabled by a second independent flag.
5. Drafts are user-bound, immutable, expire after 15 minutes, and limited to 50 outstanding records per owner.
6. Confirmation is a row-locked transaction. A replay returns the prior saved record; an expired or foreign-user draft fails.
7. Tools **cannot** approve their own drafts. The user opens PRP `/me/mcp-approve/{draftId}`, reviews the immutable JSON data, enters the PRP password, and receives server-side `APPROVED` (wrong passwords are capped at five attempts per draft). The MCP tool can only confirm `APPROVED` drafts. The UI never sends the password to the MCP tool or AI provider. The user can reject/revoke before consumption. Keep production write-enabled=false until this flow is verified end-to-end with transport identity propagation and request protections.
8. No direct SQL tool, update/delete business mutation tool, arbitrary SSRF target, or backend API key in a prompt.
9. For external clients, add OAuth 2.0 authorization-server support (scopes/PKCE, token audience, refresh/revocation, discovery), explicit origin/Host validation and request budgets before opening public access.
10. Audit actual MCP use and gate sensitive wellness/financial scopes before broad multi-user enablement; avoid recording full tool arguments or secrets.

## Exact approval sequence

1. MCP `prp_prepare_*` returns a 15-minute draft ID and the exact proposed values.
2. Open `https://micor.top/prp/me/mcp-approve/{draftId}` **in a trusted PRP browser**, not an AI tool. Authenticate to PRP if necessary.
3. Review exact values, enter the PRP password and click the approval button. Only the PRP server changes `PENDING` to `APPROVED`.
4. Ask the MCP client to run `prp_confirm_draft({ draftId })` (no approval boolean). A transaction changes `APPROVED` to `CONSUMED` and returns the saved record.
5. To cancel: reject the pending/approved draft in PRP before confirmation.

Any MCP client with the authenticated bearer alone cannot approve unless the account password is also known. Password reauthentication is a **step-up proof**, not a substitute for implementing OAuth 2.0 and token-bound scopes. Rate limiting and logs must additionally be reviewed before public exposure.

## Local checks / gate to next milestone

```bash
cd app/backend
mvn -q -Dtest=McpGatewayTests test
cd ../..
node app/scripts/verify-db-migrations.mjs
```

Then, against an isolated migrated test database:
- Unauthenticated initialize/tools/list/tools/call must receive 401.
- Authenticated user A must not list user B data or confirm B's draft.
- Feature flag OFF must return unavailable; write flag OFF must block prepare/confirm.
- Explicitly approved draft commits **once**; replay returns same ID; expired and malformed draft IDs fail.
- Concurrent confirmation from two clients creates one record.
- Verify authenticated identity remains present in MCP tool handler execution.
- Test real MCP initialize, tools/list, tools/call and response formatting using MCP Inspector.
- Verify JDBC and MyBatis use the **same transaction** for confirmation/replay behavior; verify the production V24 plus MCP V25–V27 lineage on a restored copy.
- Audit finance input matching and merchant/category handling with real business service constraints.
- Recheck release controller's migration compatibility policy and restore evidence before promotion.

## Next milestone

Finish OAuth 2.0 (authorization-code+PKCE, discovery, client registration policy, resource audience, scopes, refresh/revocation), an independent host/Origin policy, audit/observability, and authenticated **real Streamable HTTP** multi-tenant integration tests. Only then consider remotely enabling production MCP writes.


## OAuth resource-server implementation (opt-in; requires an external authorization server)

The MCP protocol handler has a dedicated Spring Security OAuth2 JWT resource-server chain **only** for `/api/mcp` when `MATRIX_PRP_MCP_OAUTH_ENABLED=true`. Legacy PRP JWT authentication continues to serve the existing application; OAuth MCP requests never fall back to regular PRP JWTs. OAuth access tokens must pass issuer, expiry, signature/JWKS and **exact canonical resource audience** checks. The signed `prp_user_id` claim maps to a currently enabled PRP user. OAuth read/write scopes are enforced **individually at every MCP tool**, not merely on `tools/list`.

```properties
MATRIX_PRP_MCP_ENABLED=false
MATRIX_PRP_MCP_WRITE_ENABLED=false
MATRIX_PRP_MCP_OAUTH_ENABLED=false
# Configure ONLY with a separately secured, trusted real authorization server:
MATRIX_PRP_MCP_OAUTH_ISSUER=https://issuer.example.org
MATRIX_PRP_MCP_OAUTH_JWK_SET_URI=https://issuer.example.org/.well-known/jwks.json
MATRIX_PRP_MCP_OAUTH_RESOURCE=https://prp.example.org/api/mcp
```

The advertised RFC 9728 discovery URL is `https://prp.example.org/.well-known/oauth-protected-resource/api/mcp`, which declares the protected resource and external authorization server. Replace placeholders only after confirming the real public reverse-proxy route, issuer policy and tenant isolation. A regular app login/refresh token is **not** a remote MCP OAuth access token.

Defined scopes: `prp.tasks.read`, `prp.finance.read`, `prp.wellness.read`, `prp.write.create`, `prp.write.status`, `prp.write.confirm`. Scope claims are trusted only after OAuth JWT signature+issuer+audience verification. A token must have an issuer-provisioned `prp_user_id` claim with explicit, verified account linking; using model-supplied user IDs is prohibited. No public OAuth authorization endpoint, dynamic client registration, account-linking consent UX, grant/revocation management or self-hosted authorization server is implemented by this PR.

**Request-thread identity:** Spring AI dispatches MCP tool handlers via workers. A Servlet security ThreadLocal may not propagate. The OAuth security chain installs a dedicated verified-principal capture filter after Bearer token validation, binds the identity to the **current servlet request only**, and the MCP transport records this trusted attribute into an immutable request context. Each tool handler validates that identity and temporarily restores the Spring Security context for the business Service invocation, cleaning it up in `finally`. Never infer identity from `_meta`, model arguments, raw client headers or static/global ThreadLocals.

**Production gate:** Do not enable MCP/OAuth until a real external authorization server is configured with authorization-code+PKCE, scopes, trusted PRP account mapping, token lifecycle/revocation policies, public origin/host and reverse-proxy agreement, plus real network integration with a compatible MCP client. Unit tests using a mocked JWT decoder prove Spring authentication and scope wiring, not real issuer signature rotation or full interactive authorization.


## PRP-owned OAuth client grants (V26, opt-in)

V26 adds only `prp_mcp_client_grants`: `(user_id, client_id)` primary key, approved scopes, ACTIVE/REVOKED status and timestamps. The database never stores OAuth access tokens, refresh tokens or PRP passwords. V26 follows immutable production V24 and MCP V25 and is pinned in the reviewed additive migration policy.

With OAuth and MCP enabled, an authenticated PRP user can open **我的 → MCP 客户端授权** (`/me/mcp-clients`) to approve a known OAuth `client_id` and an explicit subset of supported MCP scopes after reentering the PRP password. The same owner can downscope or revoke a grant. These are ordinary PRP JWT-protected browser APIs, **not** MCP tools; no agent can silently approve itself.

- `GET /api/mcp/clients`: show the current user's grants, including revoked ones.
- `POST /api/mcp/clients`: `{clientId, scopes, password}`; password reauthentication is rate-limited with existing PRP login attempt safeguards; maximum 12 active clients.
- `POST /api/mcp/clients/revoke`: `{clientId}`; owner-scoped, idempotent revoke.
- Every external OAuth bearer request must have a valid issuer-signed `client_id` and a matching **ACTIVE** PRP owner grant. The granted authorities are the **intersection** of signed OAuth token scopes and owner-approved PRP scopes. Empty/revoked grants cause authentication failure even if an access token is unexpired. The lookup is performed for each request, not served from an authorization cache.

**Important trust boundary:** This per-client permission table is PRP-side *consent enforcement*, not a complete OAuth authorization-code/PKCE grant, identity-provider subject-to-user enrollment, or OpenAI client registration. It still depends on the trusted issuer issuing a correct, signed `prp_user_id` and `client_id` claim. Do not approve an unknown client's ID or enable public MCP while external issuer account linking and token lifecycle remain unverified.

Verification should cover wrong passwords, unsupported/duplicate scopes, cross-user revoke failures, reduction of previously granted scopes, and immediate rejection after revoke on a still-unexpired signed token. User credentials and OAuth token values must never appear in application logs or AI tool arguments.


## V27 — Verified OAuth issuer/subject account linking

The MCP resource server no longer trusts an externally signed `prp_user_id` as sufficient proof of PRP account ownership. Instead it maps the **verified OAuth issuer+subject** to a PRP user through a separate, owner-authorized proof-of-control exchange:

1. The PRP owner logs in through the normal app, approves a known OAuth client ID and allowed scopes, then opens `我的 → MCP 客户端授权`.
2. The owner reenters their PRP password and requests a ten-minute, **single-use, 256-bit** client-bound linking ticket via `POST /api/mcp/identity/tickets`. Only a SHA-256 digest of the ticket is stored; the raw secret is displayed once in PRP and should not be logged or pasted into a normal AI conversation.
3. The external client separately obtains a signed **access token** through the OAuth issuer's Authorization Code + PKCE flow. To bootstrap, it invokes `POST /api/mcp/link` with Bearer and `{"ticket":"..."}`. The dedicated OAuth SecurityFilterChain verifies the token's signature, issuer, expiration and MCP resource audience, captures the verified JWT in the current Servlet request and passes its signed `issuer`, `sub`, `client_id` to the linking service. It never accepts raw user IDs or subjects from request JSON.
4. An atomic transaction locks the ticket, verifies its expiry, owner and exact signed client ID, rechecks that the owner's PRP grant is still active, and enforces one external subject per PRP owner per issuer and one owner per issuer/subject. The mapping is stored in the additive V27 `prp_mcp_identity_links` table; the ticket is marked consumed exactly once.
5. Future OAuth requests resolve the PRP account **only** through this verified mapping, recheck enabled account status, then intersect issuer-signed token scopes with the owner's active V26 client grant. Unlinked, revoked or mismatched identities fail closed.
6. The owner can view mappings at `GET /api/mcp/identity`, or reauthenticate to unlink through `POST /api/mcp/identity/unlink`. Revoking the client grant also blocks new MCP calls immediately, independently of identity unlinking.

This is an explicit owner-controlled **account-link bootstrap**, not a public OAuth authorization server. It requires an actual external issuer and compatible client to authenticate and submit the code. Public ChatGPT MCP write support depends on ChatGPT plan entitlements; no such access is implied by local PRP implementation.

### Isolated OAuth authorization-server reference

`app/deploy/mcp-oauth/` includes a **staging-only** Keycloak 26.8.0/PostgreSQL Compose example (loopback-only port, private environment secrets), an empty locked-down realm starter, and a read-only issuer metadata + PKCE S256 + public JWKS preflight with offline CI fixtures. Keycloak's client ID metadata document and resource-indicator support are experimental in this version and require explicit operator review. This does not create external users/clients, configure DNS/TLS, add Nginx routes, obtain OAuth tokens, or touch PRP production services.

Remaining release gates: external issuer and client registration/PKCE/consent configuration, live signed token and key rotation tests, exact public Host/path matching, secure user bootstrap UI verification, request audit/throttling, and the existing production preservation controller/SSH release hold.
