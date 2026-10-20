# PRP-AI-02 · Safe, owner-scoped invocation telemetry

## Dependency
This change is stacked on PR #82 (`feat/prp-ai-01-model-gateway`).
The PR temporarily targets `main` because repository CI only runs for PRs based on `main`.
Do not merge #83 before #82: the temporary diff includes #82's code, and will shrink
once #82 is merged. Rebase only if needed after merging #82.

## Scope
- `ObservedAiModelGateway` is `@Primary` and instruments the existing model invocation
  without changing the HTTP/SSE contracts or the provider clients.
- Records metadata only: owner ID, provider/model ID, credential-source classification,
  success/failure, allowlisted failure category, total model call elapsed milliseconds,
  first nonempty streamed delta latency, reported input/output tokens and timestamp.
- Empty upstream usage is represented by SQL NULL (unknown), **not billed at zero**.
- `GET /api/ai/telemetry?days=1|7|30&limit=1..50` is authenticated, owner-scoped,
  returns no-store, aggregates and recent details.
- Adds a read-only AI settings telemetry panel. Provider pricing is not source-verified
  and **cost is intentionally unavailable**; do not claim that these token totals equal
  provider invoices.
- V23 adds `prp_ai_invocation_log`; 30-day bounded batch retention removes old metadata.
- The audit path is best-effort: a missing table or failed write cannot interrupt model
  responses, and no exception body, prompt, model output, tool result or key is logged.
- Initial coverage: Gateway streaming calls including model connection tests. Separate
  provider-native tool planning, wellness structured/vision and practice AI generation
  need future adapter instrumentation. ElapsedMs excludes queue admission, tool
  planning and application-level operations; firstTokenMs is null if no delta arrives.

## Rollout and verification
- Run CI full Maven/Web/Mobile/MySQL migration/legacy-preservation checks, plus
  /api/ai/telemetry auth and cross-user tests.
- Existing production databases require a verified backup, Flyway baseline/validate
  and **explicit V23 migration** before enabling read-side telemetry. Do not let a
  GitHub merge imply deployment; never use Flyway clean/auto-baseline/unsafe repair.
- Manual provider smoke tests: DeepSeek legacy/personal, Claude, other provider and
  connection-test route; full SSE response unchanged, no telemetry credentials.
