# Personal OS T-005: reviewed one-shot model advice (Draft)

Parent requirement [#181](https://github.com/micor-cjj-spec/matrix-prp/issues/181), task [#186](https://github.com/micor-cjj-spec/matrix-prp/issues/186). This independent stacked branch builds on [#208](https://github.com/micor-cjj-spec/matrix-prp/pull/208), which in turn depends on review-only [#206](https://github.com/micor-cjj-spec/matrix-prp/pull/206). **NO MERGE / NO DEPLOY / NO PRODUCTION AUTHORIZATION.**

## First-party REST flow

All endpoints require an authenticated PRP user; HTTP responses include `Cache-Control: no-store`.

1. `POST /api/ai/personal-os/goals/{goalId}/model/preview` with `{"includePersonalFacts":false}` (default): build the current owner-scoped career-goal snapshot using the T-005 local evidence preview; return exact JSON snapshot, selected provider/model, expiry and random preview ID. **This does not call a model.** With true, include only the existing vetted NORMAL + CONFIRMED + current owner facts.
2. User inspects the actual outbound snapshot **and provider/model**, then clicks the explicit confirmation control. `POST .../model/confirm` with `{"previewId":"..."}` consumes that preview and creates a new one-use model token. **Confirmation does not call a model.**
3. `POST .../model/suggest` with `{"modelToken":"..."}` consumes the token atomically, rechecks owner/goal/provider/model and **rebuilds the snapshot**. Missing/changed/revoked facts fail closed before any external call. The selected provider is then invoked once using the existing model gateway, monthly request/token quota reservation and no tools. The response is checked before display.
4. Any retry or data change requires a fresh preview and explicit confirmation. Tokens expire after three minutes and are process-local; a restart or multi-instance handoff requires a fresh approval.

The dedicated POST routes are excluded from MCP in `app/config/mcp-capabilities.json`. No OAuth scope, Keycloak grant, Flyway migration, personal memory write, task create/update or production behavior is enabled by a draft PR.

## Trust boundaries

- Reviewable snapshot has bounded size; it is derived exclusively from existing owner-checked Goal/Memory services, not from browser-supplied facts or a free-form model query.
- Only the inspected snapshot is provided to the model as **untrusted data**; no chat history, health or finance context, private memories, credentials, or task/record/review bodies are exported.
- Goal/evidence strings may themselves contain prompt injection; the system instruction labels them as data. Model output is untrusted and strictly parsed as 1–3 proposal drafts. Every evidence reference must match the inspected snapshot exactly; fabricated references, extra output fields, or invalid JSON are rejected. This cannot guarantee the model never misunderstands a malicious fact, so **the proposals remain suggestions for human review only**.
- Suggestions contain verified reference IDs, explicit assumptions, and missing-data notes; no automatic conversion into tasks. A future integration must use a separate existing user-approved task draft flow.
- Provider charges may occur after a validated model-token invocation; retries of the same token are rejected. The normal AI request/token budget applies.

## Verification required before merging any dependency

- Java compilation, unit tests, CI and feature-impact registry on exact SHA.
- Synthetic unauthorized, cross-user, wrong-goal, model-switch, snapshot-revision, replay, prompt-injection-as-data, fabricated citation, malformed schema checks.
- Confirm no production deployment, no key/OAuth/MCP capability changes and no user data in GitHub.
- T-006 model-facing tools remain separately blocked; T-007 full first-party PWA approval experience, actual provider smoke test, real goal→action→review and independent security review are **not completed here**.

This is an incremental T-005 implementation candidate, **not an assertion of T-005 complete or production-ready**.
