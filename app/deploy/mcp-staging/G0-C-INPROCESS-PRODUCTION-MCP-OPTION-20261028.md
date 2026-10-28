# G0-C alternative — in-process MCP on the existing PRP application (2026-10-28)

> **DESIGN/CI EVIDENCE ONLY — NOT AN APPROVAL OR DEPLOYMENT.**
> PR #113 remains Draft, production backend/data unchanged, G0/B2 NO-GO.
> This document supersedes any claim that a separate production task-read
> bridge is *required* to reach the actual user's existing PRP tasks.

## Latest running V2 parity and real-data target, observed 2026-10-28

The operator ran immutable `live_v2_artifact_readonly.py` from
`4d6fba554aa87f83ac5ccd77c07cb76252b16133` on the **actual**
`prp-mcp-v2-gateway-1` and `prp-mcp-v2-backend-1` containers.
Both were `running=YES`, but both reported `oidc=ABSENT`;
`artifacts_feature_ready=BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE`,
`docker_state_changed=false`, `g0_b2_install_permitted=false`
and the outer read-only shell completed. This definitively rules out
using the currently deployed V2 images for first-party linking; do
not treat `200 text/html` SPA fallback as proof the callback is present.

The independently operated current test Realm database clone *did*
restore 101 tables, preserve 13 clients and match signing public JWKS;
the two reviewed OAuth clients were created and rolled back **only in
the clone**. This resolves current-snapshot technical recoverability,
not genuine original G0/B2 approval or deployment.

**Target principle:** The user requested their **existing** PRP owner's
real task data, not a new synthetic account. The isolated 18082 V2
database and never-installed 18083 NewDB are not proven to hold that
owner's real task rows. **No new PRP data copy, cross-database join,
public producer endpoint, owner-identity shortcut or production Flyway
migration is authorized by these facts.**

The low-complexity **design recommendation**, conditional on review
of true schema and recovery, remains one in-process **task-only**
MCP resource in a safely upgraded existing PRP application against
its own production `matrix_prp` owner/task store. It uses the original
service-level tenant authorization and avoids adding a second
producer/delegation bridge. **This is a more consequential production
release than upgrading the isolated test V2**: review independent
backup/restore, actual running code lineage, full V7-baselined schema,
V8–V24 checksum parity, V25–V28 additive migration, fail-closed
feature flags, Nginx/Keycloak public issuer design, owner-consent
binding, and a no-data-loss rollback before any change.

**Single next metadata check (with independently authorized SELECT
access):** The actual production database was last observed as a
rank-1 V7 Flyway BASELINE plus 17 successful V8–V24 SQL migrations,
but their stored checksums were never reconciled. The already
checked-in fixed, one-statement
`production_v24_crc_aggregate_readonly.sql` compares only Flyway
metadata to the reviewed source, returning schema/row counts and a
`SOURCE_CRC_MATCH_REVIEW_ONLY` vs `BLOCKED_OR_UNVERIFIED` decision
with `deployment_permitted=NO`. It does not query tasks/users or
reveal raw history/checksums. Do not run it with an unreviewed
unpinned Git source, a root DB login as a substitute for SELECT-only
authorization, or on the legacy isolated staging schema. A matching
CRC still cannot prove prebaseline V1–V7 DDL or source/JAR
attestation, and is **not** permission to migrate.

No need to rerun the completed Keycloak recovery or the V2 missing
marker test absent new evidence. G0/B2 remain NO-GO.

## Production owner-FK DDL metadata now confirmed on live MySQL (2026-10-28)

The operator has completed **both distinct** live production read-only
preflights on `matrix-mysql` / `matrix_prp` using exact pinned Git
SQL and the existing authorized login:

1. `production_v24_crc_aggregate_readonly.sql`: **17/17**
   original V8–V24 migration script names, ranks, success and signed
   CRC checksums matched the reviewed source; exactly one V7
   baseline and 18 successful history rows.
2. `production_v24_mcp_ddl_shape_readonly.sql`: actual
   `prp_users(id)` is single-column signed BIGINT primary key,
   InnoDB/nonpartitioned; **zero** proposed five-table collisions,
   **zero** proposed five-FK-name collisions, zero V25–V28
   history entries, all 18 history entries successful.
   Exact decision:
   `V25_V28_FK_DDL_SHAPE_MATCH_REVIEW_ONLY` with
   `deployment_permitted=NO`.

This resolves the **known source CRC** and **specific owner FK/DDL
name** compatibility uncertainties; it does not certify all
pre-V7 DDL, populated production data semantics, deployed
JAR/migration source, owner/task preservation through migration,
restore, public OAuth, or any G0/B2 authorization.

**Next operation must be reviewed independently** because it concerns
the user's production application and potentially sensitive full
database data: assess production backup consistency method, complete
schema scope, secure storage, free disk/memory, expected lock/time
impact, backup integrity, and reversible application/runtime release.
Then create and recover an isolated private **production-data clone**,
verify row digests and owner-task relationships privately (never print
task data), and test only there V25–V28 and the actual production
V7-baseline sequence. Keycloak **test** database recovery evidence
is separate and does not replace a PRP MySQL backup or data recovery
test. Never use the old isolated V2 schema with conflicting
historical MCP V24 migrations.

No further identical metadata/Keycloak tests are required unless
the state or approved code changes. The initial MCP functionality
should still be **read-only tasks** on original PRP owner data only,
with feature flags off until authorized deployment. PR remains Draft;
G0/B2 remain NO-GO.

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

## Runtime OAuth tool catalog exposure — tasks only by default

Code review found that `McpToolConfiguration` originally registered
**all 11 MCP tools**, including finance, wellness and writing, even
when OAuth resource metadata advertised only `prp.tasks.read`.
Individual `McpScopeGuard` checks prevented unauthorized execution,
but the client-visible `tools/list` surface violated the phase-one
least-privilege *discovery* goal.

The Draft-only fix now selects the tool registry through an explicit,
fixed **tool name → required advertised OAuth scope** allowlist.
The default `MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES=prp.tasks.read`
registers **only** `prp_tasks_list` and `prp_task_get` in OAuth mode.
Finance, wellness and every write tool are not registered and cannot
be invoked as a recognized MCP tool. Other categories require
independent explicit advertised scopes; write scope configuration
also requires `MATRIX_PRP_MCP_WRITE_ENABLED=true` and actual client
consent. For every permitted tool the OAuth bearer/grant and
per-tool owner/scope checks remain required. The old, isolated
legacy-JWT test mode intentionally retains its original registered
tool set for backward compatibility; it cannot be activated
without OAuth in a non-test runtime due to `McpActivationGuard`.

[Spring MockMvc OAuth tools/list plus tool-call regression 40607154558](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40607154558)
**SUCCESS**: 20 Java tests (including four tool-manifest scope tests
and six Spring Security tests) show that only the two task tools
are listed by default; finance/write calls return `Tool not found`
without touching finance or draft services. This is still a
**disposable test environment**, not evidence of production
ChatGPT consent, installed Nginx or a deployed PRP image.

## Populated pre-MCP database migration rehearsal (2026-10-28)

[Real disposable MySQL incremental upgrade CI 40608149044](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40608149044)
**SUCCESS**. This is a stronger, distinct verification than
fresh-empty-schema V1–V28 tests:

1. Before running any SQL, the CI workflow validates that the
   historical migration **Git blobs V1–V24 match `origin/main`
   exactly (24/24)**, and the Java fixture verifies its *exact*
   loopback, CI-specific MySQL URL/schema and temporary-runner flags.
2. A newly created MySQL 8.4 database runs genuine Flyway
   **V1–V24** to simulate an existing production-version schema,
   then inserts **synthetic historical business data**:
   2 owners, 27 tasks (24 and 3), a finance transaction, a
   video asset and a vocal song. It computes stable row digests and
   snapshots the original history checksum/script/versions.
3. Running the proposed same-code Flyway V25–V28 against the
   **already populated** database applies **4/4 new migrations**
   and reaches v28. Subsequent validation checks 28/28, unchanged
   V1–V24 checksums, identical owners/business row digests, the
   exact **five new MCP tables**, no removed legacy tables,
   and correct FK targets for existing PRP owners in client grant
   and identity link records.
4. The disposable Docker MySQL container is cleaned up by the
   runner-owned workflow. No persistent PRP data, actual user JWT,
   Keycloak, existing MySQL or live service is contacted.

Actual job log: `Successfully applied 24 migrations ... v24`,
then `Successfully applied 4 ... v28`,
`PASS CI_SYNTHETIC_POPULATED_V24_TO_V28_DATA_PRESERVED=YES`,
**1 JUnit test, 0 errors, BUILD SUCCESS**.

**Mandatory limitation:** this is a clean GitHub checkout seeded
with small synthetic business rows. The operator's current
`flyway_schema_history` might contain older manually applied
SQL or version/checksum drift; its production DB engine, schema
constraints and real dataset may differ. This success does NOT
authorize running Flyway on that existing volume. First obtain
read-only production history/DDL evidence using the protected
change-control process, create and verify a backup and a
separately isolated restoration, and repeat on that authorized
populated replica before any installation. A production rollback
must account for post-upgrade writes, not blindly restore an
older backup over newer records.

## Production Flyway history read-only inventory (2026-10-28)

The last successful populated-schema CI is not evidence of actual
operator-host history. A **separate, explicitly authorized read-only
inventory** remains required. Review
[PRODUCTION-FLYWAY-READONLY-PREFLIGHT-20261028.md](PRODUCTION-FLYWAY-READONLY-PREFLIGHT-20261028.md)
for a pure `SELECT` statement and a **no-database-client** local
analyzer. The analyzer rejects wrong V24 staging lineage, failed or
missing installs, partial MCP history, duplicate versions and wrong
schema. It intentionally **never validates Flyway CRC checksums** or
returns a release-approval exit code (2 = blocked, 3 = source-history
shape matched but still unverified).

[Actual disposable MySQL SQL-export + offline-parser CI 40609653162](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40609653162)
**SUCCESS**: genuine Flyway metadata query after the simulated
populated V24 → V28 migration was parsed as `V28_SOURCE_HISTORY_SHAPE_MATCH_CHECKSUMS_UNVERIFIED`,
with `deployment_permitted=false`; the expected process status
was deliberately 3. Nothing was read from the operator's actual
database. Production checksums, DDL and backup restore must still be
independently verified and signed before any real upgrade.

## Independent source CRC parity (2026-10-28)

The older Flyway preflight checked only migration version/script names.
It now **optionally** compares the selected production-history metadata
with reference CRC32 values computed from SQL files in the **same
reviewed source checkout**, using `--verify-source-crc`. The candidate
algorithm was tested against **all 28 real Flyway-installed checksums**
on a disposable, populated-schema MySQL 8.4
[CI 40610322642](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40610322642)
(**SUCCESS**). An exact source CRC match returns **exit 4**, never an
install authorization; checksum drift/malformed history returns **2**,
and a name-only match without CRC requested returns **3**.
The output never contains user data or raw history.

This parity proof does **not** show which SQL migration resources
are inside the actual installed production JAR. The reviewed branch,
build artifact, true production `flyway_schema_history`, custom
placeholders/legacy repair history and backup DDL still need an
independent lineage review and restored-copy rehearsal. Current
G0/B2 **NO-GO** remains in force.

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
