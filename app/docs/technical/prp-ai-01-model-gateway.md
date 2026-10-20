# PRP-AI-01 · Model Gateway compatibility foundation

## Scope

Introduce `AiModelGateway` and `DefaultAiModelGateway` as an application-owned interface
between the chat/settings services and their existing provider HTTP clients.

- `AiService` uses the gateway for streaming. Legacy server-key DeepSeek still uses
  `DeepSeekClient` and personal/other providers still use `AiProviderClient`.
- `AiSettingsService.test` continues using the configured-provider adapter for all models,
  including DeepSeek, preserving the current API-key connection-test behavior.
- Neither the SSE contract nor the session persistence, context consent, usage reservations,
  provider authentication, or error handling semantics change.
- No schema migration, environment variable, new dependency, or production deployment is needed.
- The legacy and configured targets are exclusive. A misconfigured target is rejected.

## Verification

Run `cd app/backend && mvn test`, plus the Web build and existing CI checks.
Check legacy DeepSeek SSE, user-key Qwen/Claude streaming and model connection tests,
provider failures (no implicit retry), worker-queue admission, historical conversations,
health AI drafts, and tenant authorization.

## Follow-on work (not in this PR)

1. Move structured/vision `WellnessAiDraftService` calls and the separately metered
   `PracticeAiService` behind an extended typed gateway, with baseline compatibility tests.
2. Add safe request-level telemetry and per-provider error/latency metrics (PRP-AI-02).
3. Experiment with an isolated Spring AI adapter only after compatibility tests pass.
   Do not switch frameworks or production traffic as part of this PR.
