# Personal OS T-006 — minimal read-only MCP tools (DRAFT / NOT ACTIVATED)

Tracks [REQ #181](https://github.com/micor-cjj-spec/matrix-prp/issues/181) / [T-006 #187](https://github.com/micor-cjj-spec/matrix-prp/issues/187). This candidate is stacked on the **unmerged, review-only Personal OS V31 release candidate #206**, not the production main branch.

**NO MERGE, NO DEPLOY, NO KEYCLOAK CHANGE, NO OWNER DATA EXPORT APPROVAL.**

## Scope and interfaces

The only new OAuth scope recognized by the backend contract is `prp.personal_os.read`. It is **not included** in default `matrix-prp.mcp.oauth.advertised-scopes` and must not be added to production health-only metadata, Keycloak configuration or owner grants without separate review.

| MCP tool | Input | Output | Privacy/limits |
| --- | --- | --- | --- |
| `prp_goals_list` | None | Up to 20 career-goal summaries | No goal description, success-criteria text, unrelated health/finance goals |
| `prp_goal_context` | Exact positive owned career goal ID | Up to 20 verified relationship summaries | Reuses `GoalService.get/context`; checks ownership, NORMAL/CONFIRMED/current and source/related reference ownership; no task/record/review body |
| `prp_memory_search` | Required keyword, 1–64 characters | Up to 10 owner-confirmed current NORMAL person literals | Reuses `PersonalMemoryService.listCurrent`; excludes private, pending, invalid, superseded, future/expired, foreign facts; no wildcard global graph queries |

No create/update/delete/confirm methods, no model-initiated task, memory or goal writes, no new AI model outflow, no database migration. The visible summaries are **data for the explicitly authorized MCP client** and should be regarded as untrusted model context; tool results by themselves are never workflow instructions.

## Four independent prerequisites for exposure and invocation

1. Server MCP OAuth enabled and startup mode **not** `production-wellness-only`.
2. `matrix-prp.mcp.additional-read-tools-enabled=true` **AND** new `matrix-prp.mcp.personal-os-read-tools-enabled=true` (both false by default).
3. Exact `prp.personal_os.read` in the configured advertised scope set; `McpToolConfiguration` manifest is an explicit allowlist.
4. At runtime: verified OAuth request identity + token authority for the scope + the preexisting `McpScopeGuard` expanded-user/client allowlist + the owner's active per-client grant. The existing authentication transport and `McpClientGrantService` re-check are unchanged.

The production health-only manifest remains restricted to its reviewed health contract. Existing tests continue to use the historical 10-argument configuration API with the new capability disabled.

## Verification expectations

- Fail-closed static manifest: scope alone or either gate alone exposes **zero** Personal OS tools; all three appear only with both gates + scope.
- Real MCP SDK specification includes the exact three names, read-only annotation and OAuth security scheme, with no health-only capability expansion.
- Synthetic tests: wrong-user/missing-scope denial precedes any business query; foreign goals are unavailable; no raw goal descriptions; unrelated, private, pending, expired or foreign memory values do not enter search.
- Existing OAuth, wellness/health, write approval and database migration CI passes at the **exact** review candidate SHA.
- Independent security review of scope/advertisement, client grants and production isolation before any merge.
- Separate user permission for any real client authorization. Never infer consent from a GitHub PR or from a scope being recognized by the backend.

## Remaining work outside this PR

Drafted goal/memory writes through an immutable owner-approved action remain intentionally unimplemented. Real authenticated MCP+Keycloak client consent and end-to-end owner/foreign-owner tests under an isolated staging environment belong to T-007. This candidate must **not** be activated as a production feature solely because the synthetic tests are green.
