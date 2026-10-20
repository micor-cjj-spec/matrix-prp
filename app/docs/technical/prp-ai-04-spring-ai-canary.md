# PRP-AI-04 · DeepSeek canary behind existing AI Model Gateway

Stacked on PR #84. Merge #84 before this change. It imports the Spring AI
**model library only**; no starter autoconfiguration, model settings migration or
new production endpoint.

## Safe default and eligibility

Both properties default to safe values:
```properties
matrix-prp.ai.spring-ai.enabled=false
matrix-prp.ai.spring-ai.canary-user-id=0
```

Spring AI is selected only when both are deliberately configured, when the
authenticated owner matches the positive canary-user-id, **and** the requested
provider is DeepSeek with a personal (not server-managed) API key.

The original HTTP transport remains in use for everyone else (including
system-key DeepSeek and every other provider). Disable the flag to revert all
future requests to the original transport. Exceptions from a canary are
propagated; NEVER retry after a partial stream, because that could duplicate
billable requests and emitted content.

Per-request model creation avoids cross-user API-key reuse and model-instance
caches. Upstream DeepSeek host remains fixed in production. Authentication,
business tooling, SSE events, quotas and telemetry remain owned by PRP.

## Critical blocker before enabling production canary

Spring AI `Flux<ChatResponse>` completion does not expose the raw upstream
`data: [DONE]` sentinel. The existing HTTP client explicitly fails closed when
it is missing. Until an equivalent termination proof is designed, **leave the
canary OFF in production**; a successful offline streaming example is not
proof of truncation parity. Usage metadata is best-effort and incomplete usage
must not be represented as provider-billed token totals.

## Verification

CI must compile the backend against Spring AI 1.1.8, retain all existing
integration tests, and prove disabled-by-default routing, owner canary gating,
non-DeepSeek exclusion, per-user keys, and no replay on failure.

PR #84's offline fixture validates basic Spring AI sync and streaming behavior.
No real API keys, no live provider smoke test, no production flag switch or
schema migration in this PR.
