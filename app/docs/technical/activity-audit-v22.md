# PRP Activity Audit / HTTP Latency (V22)

- Authenticated MVC API calls are recorded on completion, including final servlet async dispatch for SSE. Captured: method, **route template**, HTTP status, elapsed milliseconds, owner and UTC time. Auth, public health checks and media are omitted. Never store raw URLs, query parameters, prompts, bodies, headers, tokens, IPs or stack traces.
- V14 `prp_ai_tool_audit` already records AI tool status and elapsed_ms. HTTP 200 on SSE does not prove model success; HTTP duration measures server processing time, not browser/network latency.
- GET `/api/activity/mine?days=7&limit=20` returns at most 50 HTTP and AI-tool metadata entries from the authenticated owner, 1/7/30 days, Cache-Control no-store.
- Chat @操作日志 uses one-shot preview and consent before exposing `activity_recent` (max 20 sanitized records) to the selected upstream model. Other users' logs, server files, arbitrary SQL and deployment logs are never exposed.
- V22 is additive. Follow the existing database backup, validation and production deployment gates; GitHub merge alone is not rollout authorization. Establish a retention policy before high-volume use.
