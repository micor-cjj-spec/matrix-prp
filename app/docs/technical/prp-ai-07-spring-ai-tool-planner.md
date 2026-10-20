# PRP-AI-07 · Spring AI tool proposal selection

## Scope and authorization boundary

Migrate the non-streaming tool-selection turn of `AiToolPlanner` to Spring AI
1.1.8 while **keeping business tool execution inside PRP**, never inside the
framework or provider. The model merely proposes a name and JSON arguments.

- The consent snapshot is consumed in `AiService` before any tool proposal.
- `tools.definitions(approved)` is the **only** tool schema input.
- `SpringAiToolPlanner` creates temporary schema-only `ToolCallback` objects
  that throw if invoked. It sets `internalToolExecutionEnabled(false)` explicitly.
- The returned function names and JSON objects are validated against exactly
  the supplied definitions, before PRP's existing `AiToolRegistry.execute`
  independently checks `CurrentUser`, permitted scope and per-tool args.
- `AiService` still owns read-only execution, SSE tool events, tool-audit writes,
  minimized tool observations, per-user data isolation and assistant reply.
- A single Spring AI `model.call` requests tool proposals: maximum four
  returned function calls; no model-loop or automatic second request.
- Every API key/model object is request-local. Only fixed catalog hosts are
  accessible in production. All three Spring AI SDKs have automatic retry
  explicitly disabled.

## Config

```properties
matrix-prp.ai.spring-ai.tools-enabled=true
```

The default enables Spring AI tool proposals in normal deployments. Emergency
rollback to the previous provider-native selection request:

```bash
MATRIX_PRP_AI_SPRING_AI_TOOLS_ENABLED=false
```

Existing chat transport rollback remains separate:
`MATRIX_PRP_AI_SPRING_AI_ENABLED=false`. Neither rollback changes the
stored data, user keys or permission scopes.

The `test` profile disables planner migration so existing controller tests
retain native HTTP fixtures; dedicated Spring AI loopback tests explicitly
exercise the new tool planning implementation.

## Not included

**No** write tool, direct Spring AI `ToolCallingManager` execution,
agent iteration, MCP tool execution or new authorization. Structured
wellness/vision and practice-generation prompts run on other code paths
and require separate migration. Each paid provider still needs an
explicit production credential compatibility smoke test.
