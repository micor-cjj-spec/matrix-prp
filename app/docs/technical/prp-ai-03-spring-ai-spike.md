# PRP-AI-03 · Spring AI compatibility spike (no production adoption)

## Goal
Prove whether Spring AI **1.1.9** works with PRP's frozen **Spring Boot 3.5.3 / Java 21**
baseline before touching the live `AiModelGateway`. Spring AI's 1.1 release line
targets Boot 3.5; the spike must expose binary/runtime incompatibilities rather
than silently upgrade the application.

## Isolation
- `app/experiments/spring-ai-spike/` is a separate Maven build; it is **not** a
  Maven module/dependency of `app/backend`.
- CI executes offline mock-provider tests; no real API keys are injected,
  external model calls made, tokens billed, Docker/MySQL required or settings changed.
- Existing `DeepSeekClient`, `AiProviderClient`, `ObservedAiModelGateway`, PRP
  SSE endpoints, health AI JSON drafts, tool grants and production artifact remain untouched.
- The production release packager only includes `app/backend` and `app/web`; this
  spike's Java classes are not part of the deployed service.

## Run locally
From `app/backend`, using the checked-in Maven wrapper:

```bash
./mvnw -B -f ../experiments/spring-ai-spike/pom.xml test
```

No `DEEPSEEK_API_KEY` is needed. In-process HTTP server binds only loopback
on an ephemeral port and responds to `/chat/completions`.

## Acceptance
1. Resolve Spring AI BOM and DeepSeek starter on Maven Central.
2. Instantiate the real Spring AI `DeepSeekChatModel` in a Boot 3.5.3 application context.
3. Confirm model routing, fake key, synchronous answer and streaming SSE deltas.
4. Verify the normal PRP CI remains green (including deployment preservation).
5. Record any version/API mismatch instead of modifying PRP backend or release gates.

## Out of scope / next decision
No Spring AI runtime adapter, feature flag, production routing, live DeepSeek test,
model billing, MCP, RAG or Agent framework migration is shipped in this PR.
An optional later PR could add a **disabled** adapter implementing `AiModelGateway`
if this spike demonstrates compatibility; it must explicitly preserve request
authorization, first-token telemetry, stream completion sentinels, per-user keys,
provider error semantics and quotas. No production switch without dedicated
regression and deployment tests.

References:
- https://docs.spring.io/spring-ai/reference/1.1/api/chat/deepseek-chat.html
- https://enterprise.spring.io/projects/spring-ai/1.1.9/
