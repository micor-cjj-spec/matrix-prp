# Personal OS T-005 — evidence preview, first increment (Draft)

Requirement: #181 / task #186. **Review only**. Stacked on PR #206 head `d3523e0c0c0fe1ab1e51f055153ec587f17ab4fc`. No merge, deployment, migration or MCP/OAuth scope change is approved.

## Behavior

- Authenticated first-party **POST** `/api/ai/personal-os/goals/{goalId}/preview`; JSON `{"includePersonalFacts": false}` by default. No request-supplied user ID or arbitrary graph traversal.
- Career-goal pilot only. `GoalService.get` verifies goal ownership/deletion and `GoalService.context` verifies confirmed NORMAL assertions, valid dates, current evidence and referenced entity ownership.
- The optional owner-selected fact overlay calls only `PersonalMemoryService.listCurrent`, and applies further owner/type/status/sensitivity/date checks. `listPrivate` and pending candidate retrieval are forbidden.
- Return a bounded list of evidence references, explicit unknowns/gaps, and **local rule-generated task drafts**. A missing record is **unknown**, not a zero or a verified absence.
- The preview does not call a model, persist snapshots, create tasks, modify user memory, invoke MCP tools or send data to third parties. Endpoint returns `Cache-Control: no-store`. Raw referenced task/record/review bodies are never fetched.
- No change to Flyway, Keycloak, scopes, production MCP tools, AI tool registry, or existing chat consent flow.

## Acceptance / known next steps

Synthetic unit checks cover unauthenticated denial, no implicit memory fetch, owner filtering, pending/restricted/expired refusal, missing goal and closed-goal behavior. CI is required to establish compile and regression status.

**Not complete T-005:** Natural-language model recommendations and one-time explicit outbound sharing approval remain unimplemented. Next increment should bind a selected goal ID and reviewed snapshot to existing `AiContextConsentService` preview/confirm/consume semantics, include prompt-injection and authorization tests, and ensure any generated task proposal requires explicit user confirmation. Do not treat this endpoint or Draft PR as model-sharing permission.

T-006 MCP exposure and T-007 real-scenario acceptance remain separate.
