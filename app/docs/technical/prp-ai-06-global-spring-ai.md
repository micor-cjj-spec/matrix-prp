# PRP AI · All-provider Spring AI chat transport

## Scope

This version routes **every authenticated user's ordinary chat stream and AI
model connection test** via Spring AI 1.1.8 by default. Supported model entries
are precisely the allowlisted providers in `AiProviderCatalog`:

| Provider | Spring AI transport | Completion proof |
| --- | --- | --- |
| DeepSeek (personal and server-key) | DeepSeekChatModel | `data: [DONE]` |
| Kimi China / Global | OpenAiChatModel compatible endpoints | `data: [DONE]` |
| OpenAI | OpenAiChatModel | `data: [DONE]` |
| Gemini (OpenAI-compatible endpoint) | OpenAiChatModel | `data: [DONE]` |
| Qwen | OpenAiChatModel compatible endpoint | `data: [DONE]` |
| Claude | AnthropicChatModel | `event: message_stop` |

The existing gateway still owns user identity, quota, SSE, decrypted personal
keys and invocation telemetry. The caller's key is only bound to a new model
instance for the duration of one request; destination URLs remain in the
provider allowlist. No second upstream request or post-failure replay.

## Runtime policy and rollback

```properties
# New default is enabled for all users, independent of account ID.
matrix-prp.ai.spring-ai.enabled=true
matrix-prp.ai.spring-ai.canary-user-id=0
```

Emergency rollback, before broader policy changes:

```bash
MATRIX_PRP_AI_SPRING_AI_ENABLED=false
```

Using the existing protected deployment controller, restart the service with
this override to return the **next** AI calls to their original HTTP clients.
Do not change the monthly quota, database or credentials to roll back.

`canary-user-id` remains a positive-ID scope override if necessary; 0 means
all accounts, not 'disable all'. No auto retry or fallback after an error.

## Boundaries / important remaining work

Only the **ordinary chat and model-connection-test flows** currently use
`AiModelGateway`. PRP's separate provider-native `AiToolPlanner`, wellness
structured AI and practice/question-generation workflows still need dedicated
Spring AI integration; replacing them blindly risks changing tool grants and
data handling. Production traffic for these distinct operations is not silently
migrated by this release.

All providers require their own valid API key or the configured server DeepSeek
key; switching frameworks never supplies missing credentials. Verified
loopback fixtures do not substitute for real paid-provider integration tests.
Follow-up acceptance must validate production provider behavior before treating
all routes as fully migrated.
