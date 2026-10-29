# ChatGPT ↔ Matrix PRP MCP: connection diagnosis (2026-10-29)

> **Scope changed on explicit owner request:** pause all PRP MySQL
> production backup/encryption/export/recovery work. Focus on the actual
> ChatGPT authentication and task-read connection. This is an evidence-based
> diagnosis, **not** G0/B2 installation authority. No real OAuth login,
> bearer token, user record access or production configuration modification.

## Current public OAuth transport: proven healthy for unauthenticated discovery

Two **actual GitHub-hosted external checks**, at the fixed public test
URLs and without secrets, succeeded:

- [OAuth discovery and official ChatGPT CIMD GET only
  #40794412964](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40794412964):
  `PUBLIC_GET_ONLY_METADATA_PASSED`, including canonical resource
  `https://prp-test.micor.top/api/mcp`, exact issuer
  `https://auth-test.micor.top/realms/prp-mcp`, public JWKS,
  Keycloak OIDC discovery, PKCE S256, RFC 9207 issuer identification,
  ChatGPT stable client metadata and callback. Official metadata has
  intersection `none` and `private_key_jwt`, with legacy preference
  `private_key_jwt`.
- [External no-bearer initialize challenge
  #40794606565](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40794606565):
  `PUBLIC_UNAUTHENTICATED_401_CHALLENGE=PASS`. The exact public
  `/api/mcp` returns HTTP **401** for a fixed unauthenticated
  JSON-RPC initialize, and the `WWW-Authenticate` header points to
  the exact RFC 9728 protected-resource metadata endpoint.

**Don't repeat these public checks absent network/config change.**
These are **not** authorization-code/token tests, real owner account
tests, Keycloak client-policy attestation, or an MCP authenticated
`tools/list`/`prp_tasks_list` invocation. They establish only
external discoverability, TLS/metadata consistency and denial of
unauthenticated MCP calls.

## Three independent active-connection blockers

| Order | Barrier and grounded evidence | Minimal safe next action |
| --- | --- | --- |
| 1 | **Keycloak does not recognize ChatGPT's actual client ID.** The operator observed a real ChatGPT authorization URL with `client_id=https://chatgpt.com/oauth/client.json` and received Keycloak **400 Client not found** before login. The current test Realm inventory previously showed **13 existing clients**, and both exact `https://chatgpt.com/oauth/client.json` and `prp-first-party-link` were **missing**. Client Policy Profiles/Policies were empty. | Review *one narrow option*: exact pre-registration of two clients (already rehearsed **only in a recovered private Keycloak clone**) with a reviewed test-only change authorization, or an independently reviewed strictly restricted built-in CIMD policy. Do **not** set broad wildcard domains, permit arbitrary DCR or give finance/write scopes. Re-verify installed client/policies and real OpenAI assertion after approved change. |
| 2 | **Currently running V2 web/backend artifacts cannot finish account linking.** Actual Docker read-only operator inspection of `prp-mcp-v2-gateway-1` and `prp-mcp-v2-backend-1` both yielded `oidc=ABSENT`, with the required frontend callback markers, backend OIDC controller/service and V28 resource missing. A callback URL giving SPA HTML 200 is not functionality. | Separately review and install vetted test images containing the *already written and CI-tested* first-party link implementation, with a compatible **newly staged** V28 database and exact callback routes. Never attach a new V28 JAR to the older V2 database with historically conflicting V24, and don't reroute to older 18081. Independently gated rollout only. |
| 3 | **The isolated test V2 database is not the user's existing PRP task store.** The genuine production `matrix_prp` user/task data is separate. A synthetic staged OAuth login can validate protocol but cannot prove the owner sees their real tasks. | For real task reads, review **in-process MCP integration with the existing PRP TaskService and its production owner/task store**, subject to separately authorized production app/schema upgrade, data-preservation/rollback. Do not shortcut by copying user IDs or dumping private tasks into staging. The owner has explicitly paused production database export, so this release-dependent phase is **deferred**. |

The original G0/B2 gate is still **NO-GO**, and Draft PR #113
is unmerged. Even the private current Keycloak snapshot (101 restored
tables, existing 13 clients preserved, exact two-client create+rollback)
is a recovery **rehearsal**, not the release approval or proof that
both clients are present in the active Realm. The Keycloak tests
substitute **synthetic private signing keys** in CI; they are
**not** proof of validation of a real OpenAI `private_key_jwt`.

## Lowest-risk continuation while production backups are paused

1. **Source/test work only, now complete in existing CI:** trusted
   `PrpMcpTools.listTasks` and owner-bound scope checks, task-only
   OAuth `tools/list` manifest, Keycloak auth-code/PKCE synthetic
   tests, real Chromium first-party UI, and isolated synthetic
   V7-baselined V24→V28 migrations. Preserve any passing evidence,
   do not launch repetitive Keycloak restore runs.
2. **Independently authorized test-only change later:** approve the
   two exact Keycloak clients and first-party test-site deployment
   with fail-closed `prp.tasks.read` only; preserve existing clients
   and original Nginx rollback bytes. Install the *new* frontend and
   backend artifact matching the exact tested commit and any new
   isolated compatible schema. Then test first-party account-link
   login, real ChatGPT confidential-client assertion, delegated
   token `aud`, `scope`, `iss`, `sub`, tools discovery and
   synthetic task list. **Do not** claim that authentication succeeded
   from a 200 discovery page, 401 challenge or simulated token.
3. **Real owner task data later:** PRP operator must approve separate
   app/database release and protected recovery; only then expose
   `prp_tasks_list` against existing real PRP with a verified linked
   owner. No production export or app change was requested this turn.

## Protocol reconciliation

- OpenAI's currently published [plugin authentication guide](https://developers.openai.com/plugins/build/auth)
  describes CIMD, stable callback and client ID when RFC 9207 issuer
  identification is advertised, `S256`, exact protected resource
  `aud`, and `private_key_jwt` support. The public external
  discovery test above confirms the expected stable path/metadata
  *for this test issuer*; that does **not** make the client effective
  inside the active Keycloak Realm.
- [Keycloak's current MCP/CIMD instructions](https://www.keycloak.org/securing-apps/mcp-authz-server)
  require an actual client-policy **profile** with
  `client-id-metadata-document` executor plus a **policy** with
  `client-id-uri` condition to dynamically accept URL-valued
  client IDs. Advertising `client_id_metadata_document_supported`
  alone does not create the policy or accept the exact client.
  For this user's task-only connection, the previously rehearsed
  **two exact pre-registered clients** remain the narrower design
  candidate and avoid opening arbitrary client-ID domains.
  Reconcile final choice under G0/B2 and verify actual signed
  tokens, issuer and audience before calling a real user task tool.

**Disposition:** public OAuth discovery/challenge = PASS, active
client recognition = BLOCKED (last actual attempted authorization),
running V2 owner link = BLOCKED, real owner/task data path = NOT
CONNECTED, production backup/export = PAUSED BY OWNER,
`real_chatgpt_prp_tasks_list_verified=false`,
`g0_b2_release_permitted=false`.
