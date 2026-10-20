# PRP-AI-05 · DeepSeek Spring AI stream completion proof

## Why this change

PRP's native HTTP client checks `data: [DONE]` before returning a successful
model invocation. The Spring AI 1.1.8 DeepSeek client also observes this event
at the `bodyToFlux(String)` transport boundary but removes it from the
`Flux<ChatResponse>`; simply waiting for `Flux` completion can incorrectly
accept a truncated upstream response with a preceding `finish_reason:stop`.

## Design: observe the *same* stream without modifying payload

The Spring AI client accepts an injected `WebClient.Builder`. On each canary
invocation, PRP creates a distinct builder with a response filter that inspects
the raw `DataBuffer` in place before the framework's SSE decoder. The observer
does not subscribe a second time, consume the buffer, copy its payload, change
the read position or cache API keys.

A bounded (128-byte), bytewise, newline-delimited SSE line parser recognizes
**only** a complete `data: [DONE]` control line. It tolerates boundaries
between arbitrary network chunks and CRLF line endings, does not match JSON
content containing the literal `[DONE]`, and refuses EOF after a partial
completion line. A successfully completed model Flux must be accompanied by
the observed marker; otherwise `IllegalStateException` is propagated.

**Never** automatically retry or fall back to HTTP after a partial response:
the model might have already produced billable tokens. PRP's existing
`AiService` will send a generic SSE failure event and will not append a
successful assistant message on these failures.

## Safety and scope

- Spring AI is still **disabled by default** and restricted to one explicitly
  configured authenticated DeepSeek personal-key owner.
- The endpoint is fixed to `https://api.deepseek.com` in production.
- No second AI provider request, no new secrets, no prompts/output in logs.
- No schema, user authorization, quota or frontend contract changes.
- A `[DONE]` marker proves an SSE termination signal was encountered, **not**
  perfect semantic validity of the model's answer or network health.
- Runtime cancellation and interruption errors still fail as exceptions.
- This only closes the specifically documented truncation gap; real-provider
  smoke testing, leak review and rollback acceptance are still required
  **before** enabling any production canary.

## Verification matrix

- Unit: split `[DONE]` across raw DataBuffers, CRLF, partial line, oversize
  line, false-positive `[DONE]` inside JSON.
- Loopback integration: successful completion, `finish_reason:stop` without
  `[DONE]`, early truncation, empty reply, callback failure, 429/503
  classification, and **exactly one** upstream request.
- Full CI: Java/Spring AI, web/mobile, MySQL migration safety and controller
  gates, with the live provider never contacted.
