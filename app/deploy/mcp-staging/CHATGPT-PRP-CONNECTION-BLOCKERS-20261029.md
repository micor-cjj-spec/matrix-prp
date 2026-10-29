# ChatGPT ↔ Matrix PRP MCP: connection diagnosis (2026-10-29)

> **Scope changed on explicit owner request:** pause all PRP MySQL
> production backup/encryption/export/recovery work. Focus on the actual
> ChatGPT authentication and task-read connection. This is an evidence-based
> diagnosis, **not** G0/B2 installation authority. No real OAuth login,
> bearer token, user record access or production configuration modification.

## Exact client real MCP task count and cross-owner boundary PASS (2026-10-29)

[Enhanced disposable E2E #40796810274](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40796810274)
**SUCCESS** at source revision
`908efa8dcd383e652c70782d015422649124af75`.
The earlier exact-ID full chain had checked task-tool success but not
the **actual returned task contents**. This stronger case:

- Uses the real reviewed PRP Java+MySQL implementation in CI with
  the exact `https://chatgpt.com/oauth/client.json` client ID and
  **throwaway CI-only** RSA signing key, real Keycloak-issued JWT
  and first-party OIDC owner link.
- Creates exactly **24 synthetic tasks owned by the linked PRP
  account**, plus **one separately owned synthetic task** in the
  disposable MySQL only.
- Parses the successful MCP `tools/call prp_tasks_list` result
  **as JSON business records** and asserts **exactly 20 tasks**
  all with the linked account's known synthetic task title prefix.
- Calls `prp_task_get` for the known separate owner's task ID and
  requires an explicit denial; HTTP success with a usable task
  response is a **test failure**, not an accepted outcome.
- Retains the strict advertised task-only tool catalog, finance
  denial, replay rejection, unlink + client revocation and 3/6
  parallel OIDC flow cap.

CI emitted
`CI_EXACT_CLIENT_SYNTHETIC_24_OWNED_1_FOREIGN_TASKS_SEEDED=YES`,
`CI_EXACT_CLIENT_REAL_MCP_20_TASK_LIMIT_AND_CROSS_OWNER_DENIAL=PASS`,
`CI_EXACT_CHATGPT_ID_TO_FIRST_PARTY_LINKED_PRP_TASK_TOOL=PASS`.
No real OpenAI signed assertion, user tasks, live OAuth login or
production credentials were used. This **closes a data-content
assertion gap in the synthetic full-chain test**, not the live
deployment blockers below. Do not repeat it absent code drift.

## New exact-client end-to-end proof — 2026-10-29 (strongest disposable CI)

[Exact ChatGPT client ID → Keycloak → real PRP first-party link → real
MCP task tool #40795555878](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40795555878)
**SUCCESS**. The workflow registers **the exact stable ChatGPT
client ID `https://chatgpt.com/oauth/client.json` and callback**
in a *fresh disposable* Keycloak 26.8.0 Realm. It does **not**
have OpenAI private signing keys: the temporary Keycloak client
uses an ephemeral **CI-generated RSA certificate/private key** solely
to prove protocol interoperability. This difference is explicitly
isolated; no test key or client is installed in the operator's Realm.

Against the actual disposable Spring Boot PRP backend and MySQL
database, this one uninterrupted CI ran:

1. Exact URL-form ChatGPT client ID with authentic Keycloak OIDC
   authorization code, browser-shaped login/consent, PKCE S256
   and the **synthetic** `private_key_jwt` assertion.
2. Verified **Keycloak-signed** access-token signature, `iss`,
   resource `aud`, signed `azp` and task-read scope.
3. PRP first-party owner `/api/mcp/identity/oidc/start`, actual
   Keycloak login/ID token verification, one-time `/finish`,
   subject continuity with the separate MCP bearer and a persisted
   grant for that same exact client ID.
4. Successful authenticated MCP `initialize`, `tools/list` with
   **exactly** `prp_tasks_list` and `prp_task_get`, and successful
   `prp_tasks_list` call against synthetic PRP data. The finance
   tool is **not advertised** and its unauthorized invocation is
   rejected. User unlink invalidates access, pending OIDC flow
   cannot replay, and client-grant revocation denies access.
   Six parallel link starts permitted exactly three active flows.
5. Kept **all production MySQL, test Keycloak, Nginx and live V2
   containers unchanged**; no PRP data export, production migration,
   provider keys, real OpenAI assertion or real user task read.

The first [CI attempt #40795274253](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40795274253)
failed **after** actual task-read success because the historical
negative finance-tool assertion recognized only `result.isError`.
The task-only MCP catalog correctly omits finance and returns a
JSON-RPC **unknown-tool error** instead. The test was corrected to
require **exactly two task tools** and accept only either an explicit
JSON-RPC error, a tool `isError=true` or a 400/403/404 denial.
It never treats a successful finance response as success.
The fixed entire e2e suite is green.

A separate [actual disposable Vue/Chromium first-party browser
regression #40795555935](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40795555935)
also completed **SUCCESS** at the same fixed-code commit
`e4c815c106db7c9fb6625f2c17ee8c94cfbddbb3`.
That test exercises the real SPA callback/login UI with a
synthetic test client, not the production-installed V2 SPA or
real OpenAI signing key. It independently supports that the
source first-party browser flow still works after this change.

**What this changes:** The exact stable client ID, one-time first-party
link, subject binding, scoped token decoder and actual task tool
have now been proven *together* under realistic disposable
Keycloak/PRP conditions. The previously separate CI contracts no
longer need to be inferred as a synthetic composite.

**What it does NOT change:** In the operator's active Keycloak Realm,
both exact OAuth clients were last observed missing. The running V2
frontend/backend were last observed lacking new link artifacts, and
the isolated V2 database does not hold existing production tasks.
Real OpenAI `private_key_jwt` verification, user consent and actual
`prp_tasks_list` remain **UNVERIFIED/BLOCKED** until independently
authorized and successful test-host cutover and separate original PRP
data path. G0/B2 approvals and public web/backend runtime status
remain unchanged; **do not click ChatGPT Connect yet**.

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
