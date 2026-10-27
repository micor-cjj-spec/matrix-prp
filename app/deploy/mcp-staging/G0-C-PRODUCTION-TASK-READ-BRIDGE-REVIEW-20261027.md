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
