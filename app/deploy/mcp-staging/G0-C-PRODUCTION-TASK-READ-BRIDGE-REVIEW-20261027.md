# G0-C review: production PRP task-read bridge, not a deployment (2026-10-27)

> **Source-backed architecture review only.** No server/client credential,
> new Spring endpoint, migration, domain deployment, Keycloak registration,
> Nginx route or PR merge is authorized or performed by this review.
> **G0/B2 = NO-GO; PR #113 Draft; production and live V2 unchanged.**

## Immediate objective and important correction

The user's target is **the existing production PRP owner's real tasks**,
not the empty, synthetic `matrix_prp_mcp_newdb_review` database at
`127.0.0.1:18083`. Current V2 at `127.0.0.1:18082` uses a different
isolated MySQL schema, and the deployed V2 image predates the new
first-party OIDC account-linking code. Never treat a synthetic OAuth
`prp_tasks_list` result as the owner's real production tasks.

The producer-side review manifest is
[`producer_task_read.review.json`](producer_task_read.review.json).
The JSON is **not** an OpenAPI registration or a running API endpoint:
it is a machine-inspectable **proposed** security/data contract only.

## Code audit — real current implementation

| Source (PR #113 unless stated) | Verified behavior | Consequence |
| --- | --- | --- |
| `app/backend/src/main/java/com/matrix/prp/tasks/api/TaskController.java` | `GET /api/tasks` delegates to `TaskService.list(...)`, not a 20-record task-only delegated service endpoint | Do **not** reuse or proxy it as a general service-user API |
| `.../tasks/service/TaskService.java` | `listLimited(TaskFilter,int)` delegates to repository | Reuse the same bounded service path, not a custom raw SQL adapter |
| `.../tasks/repository/MyBatisTaskRepository.java` | `buildFilterQuery()` adds `TaskEntity::getUserId == CurrentUser.id()`; `listLimited` emits SQL `LIMIT` | Per-owner SQL partitioning already exists **after a trusted producer principal** is established |
| `.../tasks/model/TaskItem.java` | fields: `id,moduleCode,title,description,priority,status,dueDate,createdAt,completedAt`; no `userId` field | Response fields can be explicitly minimized; description may contain private content and requires owner consent |
| `.../auth/security/CurrentUser.java` | gets a `UserProfile` from Spring `SecurityContextHolder` | A free-form owner ID or an MCP server's own login **cannot** become the production owner |
| `.../auth/security/JwtAuthenticationFilter.java` | existing first-party `Bearer` JWT, lookup of matching **enabled** PRP account and username | User JWT is not a safe reusable server-to-server credential or permission to read as another owner |
| `.../config/SecurityConfig.java` | `/api/**` routes (apart from explicit public exceptions) require authentication | No existing `/internal/mcp/tasks` producer endpoint; do not change general CORS or public `/api/**` exposure |
| `.../mcp/McpOAuthResourceServerConfig.java` | OAuth resource chain validates signing issuer/audience, maps verified `(iss,sub)` to **staging** PRP owner via local `McpIdentityLinkService` and checks client grants | Staging PRP owner ID != production PRP owner ID; identity mapping must be independently authorized **at the producer** |
| `.../mcp/PrpMcpTools.java` | `prp_tasks_list` requires `prp.tasks.read`, status enum, calls `tasks.listLimited(...,20)` | Existing task tool contract is reusable, but must not silently fall back to empty staging tasks on producer errors |

The owner-bound list filter and SQL LIMIT are also present in the
**current `main` branch**, despite `main` and PR #113 not having
identical task repository files. A separate draft-only single-task get
method must not be assumed to exist in the live producer.

## Actual task repository Java + fresh MySQL evidence (2026-10-27)

The new `TaskReadProducerBoundaryTests` executes the real
`TaskService.listLimited` and MyBatis `MyBatisTaskRepository` with
two *synthetic* `UserProfile` principals and a **mock Mapper**.
[JUnit CI 40536557572](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40536557572)
**SUCCESS** (3 tests): generated SQL has its own `user_id` and
`LIMIT 20`; missing trusted principal and invalid limits fail before
Mapper access.

The newer `TaskReadProducerDatabaseIT` goes further:
[disposable real MySQL 8.4 CI 40538367068](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40538367068)
**SUCCESS** (2 tests, 0 failures/errors). A GitHub-hosted runner
created a **brand-new local-only** MySQL instance and ran **all 28
Flyway migrations up to V28**. It inserted 25 tasks for one synthetic
PRP owner and 3 tasks for another, then verified real SQL result
partitioning, 20-task limit, status filtering, cross-owner task-ID
denial, and unauthorized principal denial. The runner used randomized
one-time MySQL and bootstrap credentials and destroyed its own
temporary database container. MCP, OAuth and writes remained OFF
during this test. No existing database or account was accessed.

The newer OCI-only smoke was also re-run after a bounded Nginx
startup-readiness fix: [40537966987](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40537966987)
**SUCCESS**. It still did **not** publish or deploy an image.

**Limits of this evidence:** neither Java test proves any service-peer
mTLS, producer-side verified owner delegation, genuine ChatGPT identity,
consent UX, revocation-on-read, network ingress, real-data transfer or
production task access. The MySQL CI emitted a Flyway warning that its
version had not yet declared support for MySQL 8.4; the migrations did
complete on this isolated database, but production version
compatibility remains an independent release assessment.
The review-only producer endpoint is **NOT IMPLEMENTED** and may not
be implicitly enabled on the existing server.

## Test-only signed delegation proof (2026-10-27)

[Java task-owner/cryptographic proof CI 40539725728](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40539725728)
**SUCCESS**. A new **test-sources-only**
`app/backend/src/test/java/com/matrix/prp/ProducerTaskDelegationCryptoProofTests.java`
exercises **seven tests** with randomly created disposable RSA key
pairs and signed JWTs; the existing SQL owner-filter suite ran three
more. Real `NimbusJwtDecoder` verifies RSA signature, trusted
issuer, normal timestamps and exact single producer audience before
synthetic `(issuer, subject)` → synthetic PRP owner mapping. Tests
reject invalid signer/issuer/audience, wrong `client_id` or asserted
service ID, missing `prp.tasks.read`, missing/replayed JTI,
expired JWT, unlinked/disabled owner and revoked in-memory consent.
The test suite **10/10 succeeded**. No private key, JWT, owner record
or credential is checked into the repository.

**Critical production limits:** This proof has no actual issuer service,
service-to-service authentication, mTLS/certificate binding, consent
database, atomic shared JTI replay register, accountable producer-side
PRP owner-link UX or production runtime wiring. In particular, a
signed `service_id` *claim* **is not proof of the TLS peer**, and the
test's in-memory `consents` set is **not owner authorization**.
These must be independently specified, built, reviewed and verified
before use. **The only implementation is in Java test sources, not
`src/main`; no endpoint was created or enabled.** This is
cryptographic feasibility evidence, not a G0-C or B2 approval.

## Disposable concurrent JTI and consent-epoch MySQL proof (2026-10-27)

[Real CI MySQL concurrency and revocation test 40542374007](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40542374007)
**SUCCESS** (4 total Java tests, 0 failures/errors). The new
**test-only** `ProducerTaskDelegationMysqlProofIT` ran alongside the
previous 2-test real SQL task-owner suite using a newly created
GitHub-runner MySQL 8.4 with the normal V1–V28 migrations.

- The **12 parallel synthetic invocations** sharing one JTI digest
  produced **exactly one** accepted insert into a MySQL unique-key
  replay fixture, with all other attempts rejected. A repeat after
  completion was rejected.
- A separate **producer-owner consent epoch** fixture proved
  that a subject's original epoch 7 was rejected immediately after
  revocation (epoch 8), and **stayed rejected after explicit
  reauthorization** (epoch 9). Another owner's authorization was
  unaffected; unknown subjects never resolved to an owner.
- Both fixture tables existed only inside the **exact disposable
  `matrix_prp_task_producer_ci` database**, guarded by
  `GITHUB_ACTIONS=true`, `PRP_CI_DISPOSABLE_DB_ONLY=YES` and
  `127.0.0.1:13307` URL/schema checks before DDL. They were dropped
  after testing. No Flyway migration, runtime `src/main` service,
  Keycloak client, production PRP table or ingress changed.

**This is not a deployable replay/consent design.** The uniqueness
constraint demonstrates that a *persistent shared* JTI registry can
serialize simultaneous inserts, **but** the production design still
requires issuer+client+audience-bound token digest identity, robust
clock/expiry/cleanup rules, transaction boundaries, lock ordering,
replica consistency, peak-load limits, and failure policy when the
registry is unavailable. A revocation racing a task read requires
explicit atomicity/linearization semantics; this test checks sequential
revoke/regrant only. The epoch field here is test data, **not a
cryptographically signed production token claim or authoritative owner
grant**. Signed token proof and this DB fixture have not been connected
to a real mTLS-authenticated producer request. An approved producer
must independently build, secure, test and monitor these components
before any real data access.

## Candidate architecture B (NOT IMPLEMENTED)

```text
  ChatGPT (genuine signed OAuth)
       |  [verified issuer/sub, azp, owner grant, tasks.read]
       v
  PRP V2 MCP gateway -- task read ONLY, no direct prod DB -->
       [non-public allowlisted, authenticated service channel]
       v
  PRP production service: **independent producer authority**
       1. Verify service peer and short-lived audience-bound delegation
       2. Verify production owner identity mapping, account active status
          and **owner's producer-side task-read consent**, fresh each read
       3. Reject claims/headers/query strings that choose arbitrary userId
       4. Establish exactly that verified owner in an isolated auth context
       5. Use existing TaskService.listLimited(filter, <=20)
       6. Return only approved TaskItem fields; deny finance/write
       |
       v
  Existing production MyBatis: user_id = authenticated production owner
```

The bridge must be **non-public**, opt-in OFF by default, and separately
approved by the production data owner. A workload-bound mTLS peer or
similarly strong service identity and a **producer-verifiable,
short-expiry, audience-restricted, owner-delegated assertion** are both
required, not a shared static API key. The exact trust/issuance and
revocation design are **unresolved**; do not implement an unsafe
`X-User-Id` or `?userId=` shortcut.

The bridge token must identify both a genuine service peer and a
production owner whose current task-read consent is available to the
producer. Merely asserting the same Keycloak `sub` as the staging
environment is insufficient if client subject mappings are pairwise or
the user has no approved production account association. **No trusted
external JWT or MCP client input may unilaterally choose a production
userId**. The production-side consent flow must be explicit, auditable,
revocable and require actual owner authentication.

**Provider errors are not success.** If producer identity, consent,
availability, delegation verification or service TLS fails: reject the
read; never return the staging owner's tasks, a cached production
response or fallback to a broad `GET /api/tasks`.

The proposed narrow endpoint shape in the JSON contract is
`GET /internal/mcp/tasks` with optional `status` enum and
`limit <= 20`. No owner ID accepted in body, URL, headers or tool
arguments. Strict allowlist only; no `/internal/**` or `/api/**`
wildcard public route. All MCP write/finance/wellness capabilities
remain unavailable.

## Required tests BEFORE any implementation or production change

1. Missing/invalid/wrong-audience/replayed delegation, missing service
   certificate and cross-environment issuer => **401/403 without DB read**.
2. Claimed `X-User-Id`, `?userId`, mismatched subject, missing explicit
   owner consent, disabled owner and revoked consent => **denied**;
   no header spoofing or token exchange bypass.
3. Two real **synthetic users** with disjoint tasks: task owner A sees
   only A, B only B, and service account sees none; task title/IDs not
   leaked through errors or cross-user response.
4. `limit=21`, negative limit, unsupported status, `POST`, `HEAD`,
   encoded raw URI aliases, Origin/Host mismatch, generic task/list or
   finance paths => **denied** at producer and ingress.
5. Failover/cache/retry tests: producer unavailable => fail closed,
   no fallback to isolated staging DB or previous user's response;
   request logging excludes JWT, content, URL secrets and task body.
6. Revocation effective before next call; 20-record maximum at SQL
   and serialization layer; response field minimization checked.
7. Dynamic capability disabled by default; no producer feature flag
   or route can be enabled by a PR comment or successful CI.

## Explicit pending independent decisions

- **G0-C producer data owner:** Is a new internal task-only service
  endpoint allowed at all? If so, choose owner-consent UX, verified
  identity mapping, peer authentication, trust rotation and per-call
  revoke check. Determine exact allowed task fields and data retention.
- **G0-B/B2 original controller:** approve real ChatGPT Keycloak client,
  public resource/Nginx route, original restore receipts and precise
  target revision independently; live V2 does not contain the new
  first-party link implementation.
- **G0-A optional:** an extra 18083 NewDB lab experiment has no effect
  on real production tasks and is not a mandatory step.
- **Release owner:** separately review source diff, rollback and restored
  production schema copy. Never direct-connect MCP to production MySQL
  or copy a production PRP session JWT into a staging gateway.

This contract is a security requirement document, **not** an authorization
to expose a new route. See `G0-NEWDB-V2-TOPOLOGY-DECISION-20261027.md`
for scope separation and
`app/docs/technical/mcp-flyway-lineage-reconciliation.md` for the
unresolved stateful V24 history.
