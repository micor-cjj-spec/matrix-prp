# G0 decision packet — NewDB lab versus existing V2 task-read endpoint (2026-10-27)

> **NOT AN APPROVAL.** Draft PR #113 only. G0 and B2 remain NO-GO.
> No permission is granted to deploy, merge, change active Keycloak,
> register an OAuth client, reload Nginx, modify a live MySQL database
> or enable MCP writes. The reviewer must make explicit independent decisions.

## 1. Why a single "test passed" cannot authorize ChatGPT access

Three concrete targets are **not interchangeable**:

| Target | Host loopback | Persistence and runtime | Authorization state |
| --- | --- | --- | --- |
| Legacy stage | `127.0.0.1:18081` | Historical legacy stage schema; not the target of PR #113 | Older, non-task-only advertised scopes |
| Existing V2 | `127.0.0.1:18082` | Existing isolated V2 DB and previously deployed older frontend/backend artifacts | Current external MCP resource and **review-only** first-party route both target V2; live Vue and OIDC controller/service markers missing |
| Fresh NewDB candidate | `127.0.0.1:18083` | New project `prp-mcp-newdb-review`, **empty** `matrix_prp_mcp_newdb_review`, separately named MySQL volumes | Not installed on operator host; MCP, OAuth, first-party and writes are **hard-coded OFF** |

The current reviewed `render_readonly_link_routes()` emits
**18** private HTTP upstream directives (17 exact paths plus 1 asset pattern) to **`127.0.0.1:18082`**.
The proposed new `compose.newdb.review.yaml` publishes the gateway
only on **`127.0.0.1:18083`**. They are purposefully *not connected*.
The current V2 raw-URI reviewed Nginx candidate also targets 18082,
not NewDB 18083. A script copying any of these V2 routes to 18083,
or pointing NewDB at historical V2/production credentials, is outside
the already-tested candidate and requires a **different approved diff**.

**Do not** call the current NewDB candidate "ready for ChatGPT".
NewDB synthetic tasks are not a replacement for the user's existing PRP
tasks. First-party identity linking must resolve to the actual approved
PRP owner and only its data; it cannot be inferred from a Keycloak account
name or from the task-read-only scope alone.

## 2. Evidence the reviewer may reuse without extrapolation

- [Real disposable Keycloak/PRP/MySQL account-link E2E 40505801787](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40505801787): SUCCESS for synthetic credentials, PKCE, identity mapping, scoped tasks, finance denial, revocation.
- [Real Vue + Chromium + Keycloak E2E 40505801772](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40505801772): SUCCESS for browser login, exact callback URL query scrub and the synthetic read-only task call.
- [Final CI-only OCI images 40507755945](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40507755945): SUCCESS; backend JAR contains the OIDC classes and V28; Vue/Nginx final image contains callback/start/finish assets. Images built only on GitHub's disposable runner; **no published artifact/host deployment**.
- [NewDB real disposable Compose boot 40510048879](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40510048879): SUCCESS; fresh MySQL corrected V24 vocal → V25 drafts → V26 grants → V27 links → V28 OIDC, gateway and backend healthy, no old volume in runner.
- [NewDB read-only host inventory and final tests 40511923427](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40511923427): SUCCESS.
- **Operator-reported pinned host inventory `09102540e1a457035982efd77a105f5dadb5aef2`:** at inspection time 18083 had no TCP listener or Docker TCP publish, no `prp-mcp-newdb-review` containers/networks/volumes were observed; old V2 and stage gateways present; preliminary memory/disk thresholds exceeded. Output explicitly said `deployment_permitted=false`.
- Previous Realm SQL: **13 existing clients**, the `basic`/`offline_access`/`prp.tasks.read` scope names present, and both exact desired clients **MISSING**. Source has not attested the mappers, consent, default/optional assignments, policies or live signer preservation.
- Previous B2 inventory: both expected independent receipts **MISSING**, backup dump metadata-only, `deployment_permitted=false`.

Each item is time-bound. None replaces real server release control,
current external browser TLS/SNI/Host/raw URI acceptance, current
database reconciliation, independent backups, or real ChatGPT
`private_key_jwt` and `prp_tasks_list`.

## 3. Request distinct approval decisions (do not silently combine)

### G0-A — isolated NewDB host boot only; **not** OAuth activation

Proposed future scope, subject to a separately approved, audited
maintenance transaction:

- Pin the reviewed PR #113 exact commit and separately built/published
  backend/gateway OCI *digests* (CI-only image IDs are not deployable artifacts).
- Name a responsible reviewer, install operator, rollback operator,
  approved maintenance window and abort thresholds.
- Independently verify same-host container/port/volume/network names
  again at the change instant. NewDB is a new project only, loopback 18083,
  fresh MySQL volume `prp-mcp-newdb-review_newdb_mysql`,
  no existing MySQL/Keycloak/Nginx namespace mounts or shared DB URL.
- Keep four flags OFF: MCP, OAuth, first-party binding, and write.
  Existing V2/old stage/prod services and public DNS/Nginx remain unchanged.
  The authorization must explicitly cover any host resource/storage risks.
- Record the initial docker image/config/volume fingerprints **without
  exposing passwords**, independently test backup/recovery of any data
  the host policy requires preserving, and define reversibility.
  Do not destroy the new volume casually on an unsuccessful startup.
- Only after authorized execution: local backend health, strict HTTP
  Host and /prp/api/ prefix guards, fresh Flyway V28 history, class/image
  attestation, and regression of production/legacy stage/V2.
  A green lab boot is not a permission to add any public route.

**Outcome allowed if approved and proven:** an isolated local NewDB
service with OAuth OFF and **no real ChatGPT access**. It is still not
data continuity for the user's actual PRP.

### G0-B/B2 — active Realm clients, raw-URI and first-party public routes

**A separate, later decision** is required before exposing login,
consent, callback or MCP requests to a new backend. The reviewer must
first explicitly select a *single* target data environment and front
door (V2 18082 versus a newly approved NewDB ingress 18083).
It must not combine paths to V2 with a NewDB database silently.

Before any active change:
- original Keycloak signing material and all 13 clients preserved,
  independent PostgreSQL backup/restoration attested, genuine
  `approved-install.safe.json` and `fresh-b2-restore.safe.json`
  evaluated by their original controllers, not fabricated;
- verify real current Realm policy/profile/client mappers and exact
  two-client create-only diffs; ensure any CIMD incompatibility is
  addressed by an explicitly authorized, target-only approach;
- independently review full *actual* Nginx six-file vhost lineage,
  raw request URI, precise read-only/first-party callback routes,
  Host/SNI/IPv4/IPv6/HTTP/2, outer TLS trust and aud/issuer pinning;
- preserve live V2 and the 18083 synthetic service until the approved
  rollback plan identifies the exact prior state, with pass/fail metrics.

No fallback to the unreviewed `18443` proxy, which was observed
routing PRP to legacy stage 18081. Never modify old B2 digests/receipts
to force the gate. NewDB profile activation is not B2 authorization.

### G0-C — actual user's PRP task data integration (future)

The fresh database has a **different** PRP user and task store. A
successful `prp_tasks_list` in that environment confirms synthetic
scope isolation, not the user's real tasks.

To reach actual PRP data, an independent data steward/owner must decide
between a separately approved **data-preserving V2 upgrade** (after
historical Flyway V24–V26 lineage reconciliation) or a new,
explicitly designed consented data interface/copy. Preserve original
primary keys, task ownership, authorization, task update semantics,
recovery points and auditability. Do not use direct production MySQL
credentials, raw table mounts, `flyway repair`, `baselineOnMigrate`,
automatic `clean`, volume replacement, or cross-schema joins as a shortcut.
The relevant existing source review is
`app/docs/technical/mcp-flyway-lineage-reconciliation.md`.

**A test PRP owner cannot silently become a production PRP owner.**

## 4. Gating decision record (to be filled by authorized humans)

| Required decision | Observed currently | Decision holder / evidence to record |
| --- | --- | --- |
| G0-A fresh local NewDB boot | **NO-GO: not signed** | Independent host change reviewer; bounded host/resource/install/rollback authorization |
| G0-B public browser/MCP route and target port | **NO-GO: no route decision** | Independent Nginx reviewer; exact six-file baseline and approved diff |
| B2 Keycloak active client registration/refresh policy | **NO-GO: both receipts missing** | Original Keycloak install/recovery controller, verified Realm preservation |
| Existing V2 synthetic-data continuity | **UNVERIFIED** | Database steward; restored-copy, FK-safe migration/rollback evidence |
| Actual existing PRP user's tasks | **NOT CONNECTED** | PRP data owner; explicit mapping and least-privilege authorization |
| Real ChatGPT OAuth + at-most-20 tasks call | **NOT VERIFIED** | Actual user using ChatGPT after all above gates |

Do not put real authorization signatures, backup contents, secrets,
bearer tokens, password, private key, session cookie, OIDC state or
authorization code into a public issue or ordinary chat.
Place the actual signed approval/restore/rollback receipts only
where the original protected change process requires.

## 5. Immediate next human action, without an unsafe host script

Submit **this exact G0-A-only request** to the designated independent
reviewer with the SHA-pinned PR and no host commands attached. They
should either authorize the fixed, isolated 18083 local-only experiment
or reject it with a reason and a specific missing evidence category.

Only **after** that decision, decide whether B2 needs the separate
G0-B live OAuth approval and what source-level route/data topology to
review next. The original B2 NO-GO is not conditional on a chat or
GitHub CI result. **This document is not a deployment instruction.**
