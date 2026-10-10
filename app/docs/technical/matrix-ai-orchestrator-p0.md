# Matrix AI Orchestrator P0 — DeepSeek Chat

## Scope and trust boundaries
- Web and uni-app **H5** screens call Spring Boot with the existing PRP JWT. The DeepSeek key is **never shipped to Web or iPhone**.
- Spring Boot persists user-scoped conversations in MySQL and streams DeepSeek's OpenAI-compatible SSE as `meta`, `delta`, `done` and `error` events.
- `GET /api/ai/codex/capabilities` is administrator-only and reports `enabled=false`. P0 **does not** install Codex, run shell commands, share subscription credentials, or allow agent tools.
- No access to personal finance, health notes, `knowledge/`, code, task actions or video content is automatically granted to the model.

## Setup
1. Keep a database backup and apply `app/docker/mysql/init/005-ai-orchestrator.sql` to **existing** MySQL data volumes. New installations should apply 001 through 005 in order; Docker init scripts run only for empty data volumes.
2. Set `MATRIX_PRP_DEEPSEEK_API_KEY` on the **Spring Boot service only**, e.g. in a root-readable or dedicated-user environment file injected by systemd/Docker. Never commit it, put it in frontend env files, or print it in logs.
3. Optional `MATRIX_PRP_DEEPSEEK_MODEL=deepseek-chat` (alternatively `deepseek-reasoner`).
4. Run backend tests, Web build and mobile typecheck/H5 build; check secure HTTPS streaming through your Nginx configuration (`proxy_buffering off`, reasonable `proxy_read_timeout` for `/api/ai/chat/stream`).
5. Login to Web → **Matrix AI** or H5 → 今日 → **Matrix AI**. New chat starts with a prompt; existing chats can be reopened.

### Budget guardrails
- Per user: `MATRIX_PRP_AI_USER_MONTHLY_REQUESTS` default 200; `MATRIX_PRP_AI_USER_MONTHLY_TOKENS` default 250000 **reserved** tokens.
- All users combined: `MATRIX_PRP_AI_GLOBAL_MONTHLY_REQUESTS` default 1000; `MATRIX_PRP_AI_GLOBAL_MONTHLY_TOKENS` default 1000000 reserved tokens.
- Request text <=4000 characters; last 12 messages, with history reduced to <=16000 estimated input bytes; max output 1024 tokens.
- Reservations occur atomically in MySQL before the upstream request. They are **conservative**, not a billing ledger and are not refunded when the provider fails. Usage stores provider-reported input/output token counts when a response finishes. Month is UTC.
- These are application-side quotas, **not a monetary spending guarantee**. Set a hard billing alert/budget with DeepSeek separately and set lower global limits for initial testing. Per-IP gateway rate limits, abuse detection and server metrics remain required before public launch.

## API
| Method | Route | Response |
| --- | --- | --- |
| GET | `/api/ai/conversations` | own recent 50 conversations |
| GET | `/api/ai/conversations/{id}/messages` | own last 200 messages |
| GET | `/api/ai/usage` | own UTC-month quotas |
| POST | `/api/ai/chat/stream` | SSE, JSON: `{"conversationId":null,"content":"你好"}` |
| GET | `/api/ai/codex/capabilities` | administrator-only disabled placeholder |

Responses for history and usage use the usual `ApiResponse` envelope; streaming uses `text/event-stream` and Bearer auth. Each stream sends a `meta` event with conversation ID, multiple `delta` events, and one `done` event. If the provider errors, an `error` event is sent and the user message is still recorded; users can retry manually.

## Production constraints
- Do **not** deploy until the branch's CI and real-device acceptance tests pass.
- DeepSeek receives text prompts and limited preceding turns. Do not paste sensitive credentials into chat. No per-user BYOK yet.
- API requires authentication. Role and ownership checks reside server-side, not in the Vue UI.
- The current H5 transport uses browser `fetch` / `ReadableStream`; native uni-app mini-program/App builds need a different streaming transport.
- Validate quota behavior under concurrent users, provider outage, long responses, reconnect, token expiry, iPhone Safari and Nginx proxy configurations.
- Future Codex Worker must use isolated non-root execution and explicit admin approvals; P0 intentionally does not implement job dispatch.
