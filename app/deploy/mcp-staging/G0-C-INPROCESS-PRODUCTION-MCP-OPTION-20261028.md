# G0-C alternative — in-process MCP on the existing PRP application (2026-10-28)

> **DESIGN/CI EVIDENCE ONLY — NOT AN APPROVAL OR DEPLOYMENT.**
> PR #113 remains Draft, production backend/data unchanged, G0/B2 NO-GO.
> This document supersedes any claim that a separate production task-read
> bridge is *required* to reach the actual user's existing PRP tasks.

## Executive decision

**Prefer independent review of the in-process alternative first,**
provided the production PRP data owner and release operator accept
a carefully staged **data-preserving PRP application upgrade**.

The same updated Spring Boot application can host the OAuth MCP
resource, its local PRP owner identity mapping and `PrpMcpTools`
alongside the existing `TaskService`/`MyBatisTaskRepository`,
using the **same authorized PRP application database**.

This would remove the *entire unapproved extra service-to-service
delegation bridge* (mTLS peer, separate producer endpoint,
cross-service OBO token exchange, independent consent registry and
a second PRP identity mapping). It **does not** remove the need for
correctly registered ChatGPT OAuth, Keycloak, grant/consent UX,
public ingress review, production database migration and recovery.

### Existing source and CI findings

- `main` has the existing PRP task service and repository but **does
  not yet contain** `PrpMcpTools` or `McpOAuthResourceServerConfig`.
- A GitHub tree/blob-SHA comparison found the **24 historical Flyway
  V1–V24 migration files byte-identical between `main` and PR #113**.
  PR #113 introduces exactly V25 drafts, V26 client grants, V27
  identity links and V28 first-party OIDC flows. This reduces
  **source** migration conflict risk, not the unknown current
  operator-host `flyway_schema_history` or production backup risk.
- [Real MySQL in-process read CI 40605208211](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40605208211):
  **SUCCESS** (7 MySQL-backed Java integration tests on the initial
  revision). Two synthetic local PRP owners received their own
  synthetic issuer-subject identities through the actual
  `McpClientGrantService`/`McpIdentityLinkService` persistence.
  Calls to **the actual `PrpMcpTools.listTasks`** returned the first
  owner's 20/24 tasks and the other owner's 3 tasks without a
  cross-service bridge; grant revocation rejected the next simulated
  authentication; anonymous/unlinked/lacking-scope requests rejected.
  This test **simulated already-validated OAuth claims**. It did not
  perform real cryptographic bearer verification, browser PKCE,
  true ChatGPT login, Nginx or production tasks *in this test*.
- Separate [isolated real Keycloak/Chromium CI 40525308360](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40525308360),
  [real disposable Nginx raw-URI/method CI 40530589102](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40530589102)
  and [OCI image smoke 40543400637](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40543400637)
  have independently passed. Their synthetic environments are **not
  combined evidence of a production-deployed release**.

## Comparison for the actual task-reading goal

| Target | Real tasks and owner continuity | New components | Primary release risk |
| --- | --- | --- | --- |
| **A — in-process MCP in upgraded existing PRP** | Direct reuse of the existing producer-side PRP user/task rows after a **verified safe application/schema upgrade** | OAuth resource chain, two separately reviewed Keycloak clients, local consent/identity link tables, exact ingress | Application and Flyway change affects production service; high rollback and verification requirement |
| B — isolated MCP plus private task producer bridge | Possible only with producer-approved verified per-owner delegated read | New producer API, peer mTLS, signed OBO exchange, replay table, consent/mapping, operational network, service-to-service observability | Larger distributed attack surface, identity lifecycle and additional production API |
| C — isolated 18083 NewDB | **Does not read existing tasks** | Independent empty database, synthetic tests | Useful lab only, no real user task continuity |

**G0-C owner decision:** Is upgrading the existing production PRP
app in place (after a verified restore rehearsal) permissible?
If **yes**, prefer the simpler in-process approach for initial
`prp.tasks.read` only. If **no** because production cannot
accept a backend/MCP schema release, evaluate the more complex
producer bridge separately. Do not presume either approval.

## Source-level read-only trust chain if approved

```text
Genuine ChatGPT client OAuth Authorization Code + PKCE
   -> independently registered Keycloak client / signed bearer
   -> exact HTTPS resource /api/mcp (Nginx original raw URI + method gate)
   -> in-process MCP JWT signature, issuer, aud, client identity checks
   -> local issuer+subject -> verified *production* PRP owner mapping
   -> load current enabled PRP account and task-only client grant
   -> per-request SCOPE_prp.tasks.read
   -> PRP TaskService.listLimited(filter, 20)
   -> MyBatis user_id = CurrentUser.id() against existing PRP tasks
```

The signed Keycloak subject must be linked by a **production PRP
owner authenticated through the first-party UX**, not through
query parameters, arbitrary `userId`, a staging owner ID or a
pre-existing token string supplied by a client. Actual first-party
callback must be on the **approved canonical production resource
host**, and the separate Keycloak first-party client is not
the same as ChatGPT's signed confidential client.

**Phase 1: tasks only.** All MCP write flags stay OFF; finance and
wellness scopes cannot be authorized for the initial client under
the reviewed production policy. The tool layer already checks
individual scopes; reviewer must independently confirm no configuration
or alternate chain can bypass the initial tasks-only entitlement.
No generic business `/api/**` or `/prp/**` gateway location.

## Mandatory non-host-changing preparation before any change window

1. Obtain a **fresh read-only production inventory** under the
   original maintenance process: deployed commit/JAR hash, active
   `flyway_schema_history` and schema tables, currently enabled
   PRP identity records/feature flags, true Nginx origin, Keycloak
   issuer, image digests and host resource limits. Current source
   history alone does **not** establish production state. Never
   publish passwords, task rows, refresh tokens or signing keys.
2. Take independently attested backups of existing PRP database,
   active Keycloak PostgreSQL/signing material and exact Nginx
   configuration with tested **restoration to disposable, private
   isolated machines**. Preserve original backup hashes. Never run
   `flyway repair`, `clean`, history rewrites or `baselineOnMigrate`
   to make a conflicting production volume pass.
3. Only on an authorized restored **copy**, test proposed
   V25–V28 additions after actual V24 history verification, restart
   the candidate signed image, preserve all existing tasks and
   owner IDs and perform regression of the original PRP experience.
   If production is still at V23, include original V24 vocal migration
   first; do not infer installed version from GitHub.
4. Independently review the precise production Nginx/vhost
   **six-file lineage** with new and existing paths, Host/SNI,
   raw request URI, TLS/HTTP2/IPv6 and rollback. Current 18082
   review snippet is **for a different staging backend** and must
   not be installed verbatim to route production.
5. Independently approve Keycloak exact ChatGPT
   `https://chatgpt.com/oauth/client.json` (private_key_jwt) and
   separate first-party PKCE client, confirm Keycloak client policies,
   preserve existing 13 client settings, and obtain the **original**
   protected G0/B2 recovery/change receipts. A PR comment or
   GitHub green CI is not an approval.
6. After a scoped, signed maintenance permission only: enable task
   read for explicitly consented owners, demonstrate real
   ChatGPT OAuth/link and `prp_tasks_list` (<=20), client/owner
   isolation, grant revoke and unrelated finance/write denial.
   Define rollback including **schema/data changes made after
   cutover**; never simply restore an old backup over newer user data.

## Explicit unresolved security and operational decisions

- Exact Keycloak signed ChatGPT client compatibility and subject
  matching between first-party and signed confidential client.
- Production migration/restore rehearsal on its true populated
  schema; source equality is insufficient.
- Task-only consent and any broader MCP tool exposure on the
  actual production Spring ApplicationContext.
- Reverse proxy and real public request acceptance, including
  correctly routing to the final **approved** backend, not old
  `18081`, V2 `18082` or NewDB `18083` by accident.
- Resource/capacity and deterministic rollback plan if an in-process
  backend regression impacts existing production PRP features.
- Real ChatGPT signed OAuth call and confirmation that returned
  tasks are from the actual PRP owner's live data.

**Current outcome: comparative architecture design + disposable CI
verification, NOT A DEPLOYMENT PLAN OR APPROVAL.** G0/B2 NO-GO.
