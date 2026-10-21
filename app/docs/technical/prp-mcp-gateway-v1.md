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

V24 introduces only an initially-empty `prp_mcp_write_drafts` table, including `approval_failures` (five-attempt lockout), `approved_at` and `CONSUMED` replay receipts. It is registered with a SHA-256 in the reviewed additive migration policy. V1–V23 files remain untouched; deploy **in order** on a reviewed restored copy. Do not baseline or clean the production schema, truncate any user data, bypass snapshot/diff gates, or run Flyway on a populated environment without a reviewed baseline.

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
- Verify JDBC and MyBatis use the **same transaction** for confirmation/replay behavior; verify Flyway V24 on a restored copy.
- Audit finance input matching and merchant/category handling with real business service constraints.
- Recheck release controller's migration compatibility policy and restore evidence before promotion.

## Next milestone

Finish OAuth 2.0 (authorization-code+PKCE, discovery, client registration policy, resource audience, scopes, refresh/revocation), an independent host/Origin policy, audit/observability, and authenticated **real Streamable HTTP** multi-tenant integration tests. Only then consider remotely enabling production MCP writes.
