# Phase 2 / Batch 2: owned task and record search via MCP

**Code-review artifact only.** Depends on PR #171; the parent PR already supplies an explicit default-off read-tool flag. This batch does not deploy to production.

| MCP tool | Source REST route | Scope | Limit / behavior |
| --- | --- | --- | --- |
| `prp_tasks_search` | `GET /api/tasks` | `prp.tasks.read` | TaskService.listLimited, 1–50 rows, filters status/moduleCode/priority/dueDate |
| `prp_records_search` | `GET /api/records` | **new** `prp.records.read` | RecordService.listLimited, 20 rows, 200-character body excerpts; supports moduleCode/tagId/recordDate/keyword |

- The new record permission is **independent** of `prp.tasks.read`, `prp.wellness.read` and the broad historical `prp.write.*` scopes.
- This PR only adds the scope to the backend allowlist; **it does not configure Keycloak, grant the scope to existing tokens/clients, change existing user authorizations, or expand the production OAuth advertised scopes**.
- The tools are included in `McpToolConfiguration.OPTIONAL_READ_TOOLS`, so they do not enter the effective MCP `tools/list` when `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED=false` (the default).
- Both methods independently call `McpScopeGuard.require`; the verified resource-server transport still requires a token, bound PRP owner identity, correct OAuth client, current client consent and the per-user expanded capability allowlist.
- The record repository now applies the selected limit **in SQL** for the MyBatis production repository, before fetching note rows and tags. The test repository uses the safe `RecordRepository` default method. Existing REST `list()` and `list(filter)` behavior is unchanged.
- `prp_records_search` intentionally does **not** return full journal/record contents. It truncates each content excerpt and omits unnecessary tags and timestamps. This is **partial**, not full, REST equivalence.
- `prp_tasks_search` is also partial relative to REST because it has an explicit cap; it otherwise supports the same four filter dimensions.

## Tests and acceptance

```bash
cd app/backend
./mvnw -B -Dtest=McpRecordTaskSearchOAuthTests,McpRecordReadOwnershipTests,McpOAuthToolManifestTests,McpCoreReadToolsOAuthTests,McpWellnessOAuthTests,McpWellnessAppVisibilityTests test
cd ../..
node app/scripts/mcp-api-contract.mjs --out mcp-api-report.md --json mcp-api-report.json
```

Validate OAuth tools/list scopes and tools/call successful reads, incorrect/expired/revoked grants, disallowed owner/client, invalid filter/range refusal, cross-user record isolation, and truncated sensitive content.

**Release gate:** No production enablement, Keycloak scope registration, `main` merge or deployment without a separate reviewed rollout and release approval. The current GitHub `Deploy PRP` workflow can auto-deploy after successful *main push* CI, so merging is not a deploy-neutral action.

## Remaining work

- Complete full owned record detail retrieval with separate bounded content and precise record ID/owner checks, only when approved.
- Add learning/practice read tools in the next batch with separate least-privilege `prp.practice.read` scope.
- For any newly introduced business REST API endpoint, update `mcp-capabilities.json` and provide MCP tests or a reviewed technical exclusion under PR #169's gate.