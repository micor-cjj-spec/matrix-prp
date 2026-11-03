# Legacy MCP discovery fallback

## Observed failure and scope

ChatGPT refresh_actions returned HTTP 424, reporting an inconsistent
server/discover response, upstream HTTP 200 application/json. This does not
establish that OAuth login failed or that the upstream JSON was valid MCP.

A real Spring Boot/MockMvc regression against Spring AI 1.1.8 / Java MCP SDK
0.18.3 reproduced a concrete defect: an authenticated server/discover request
with string id `openai-mcp-discover` and 2026-07-28 per-request metadata resulted
in HTTP 500, with `Missing handler for request type: server/discover`. The exact
HTTP 200 payload behind the reported ChatGPT failure was not captured. Do not
claim the local 500 reproduces that precise payload or proves this is its sole cause.

Read-only inspection of the live testing container on 2026-11-03 confirmed its
JAR uses Spring AI 1.1.8 and MCP SDK 0.18.3, without a custom discovery transport.
Running JAR SHA256:
`d2cefed386154d30188327a48e31f63c5e9999def135deac0d0374fabe773db2`.
The staging source checkout reports 1c1fdeae611fea7b7eb11c5a14d0d14931fb5f13;
that checkout alone must not be used to identify the running image's code.

## Change

The OAuth transport now installs a narrow handler decorator. Only the unsupported
server/discover request gets a standard JSON-RPC -32601 Method not found response
preserving the request ID and its type, allowing legacy initialize fallback.
It does not fabricate supportedVersions, capabilities or 2026 protocol support.
All other requests and notifications retain the SDK handler and transport.

Spring's primary transport is the decorator; the existing native WebMVC transport
continues serving HTTP routes, origin checks and trusted request context. The
decorator has no independent destroy callback; protocol versions and graceful
shutdown delegate to the native transport. No HTTP body rewriting, credential
handling, new public route or authentication exception is added.

Remove/review this shim when upgrading to an SDK with native server/discover
support; the unsupported-method behavior is intentional for this pinned legacy SDK.

## Validation and remaining work

Local tests: `./mvnw -B -ntp '-Dtest=Mcp*Tests' test`, 64 tests, zero failures,
errors or skips. These include discovery error ID/type, native initialize,
tools/list exposing prp_tasks_list, delegation, unbound/unauthenticated refusal,
and the existing scope, identity, audience, draft and MCP activation regressions.
HTTP tests use controlled JWT decoders; they are not real ChatGPT/OAuth acceptance.
Linux CI runs the same MCP suite on Java 21 without production credentials.

No application has been deployed, no Nginx/Keycloak/controller configuration was
changed, no production or staging database migration was run, and no user bearer
from screenshots was read or reused. No WARP registration was performed.

Before rollout, use the existing authorized staging procedure to bind the selected
commit to its image and review any pending migrations. Preserve the old image,
configuration, database backup/recovery proof and rollback commands; do not assume
that replacing the staging JAR cannot trigger Flyway. Keep writes disabled and
production PRP untouched. Only after controlled staging deployment and independent
health/rollback checks should ChatGPT refresh tools and invoke prp_tasks_list.
The real ChatGPT response, OAuth binding, user isolation and revocation still need
acceptance. A passing shim regression does not establish those results.
