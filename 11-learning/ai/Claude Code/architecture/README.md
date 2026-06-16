# Claude Code Architecture

> This directory stores structured architecture breakdowns after source reading.

## Purpose

Use this directory to split Claude Code into stable architecture topics. Compared with `notes/`, documents here should be more structured and reusable.

## Planned Documents

```text
architecture/
├── README.md
├── agent-harness.md
├── tool-system.md
├── context-memory.md
├── permission-safety.md
├── skills-hooks-mcp.md
└── java-spring-ai-implementation.md
```

## Topic Scope

| Document | Scope |
|---|---|
| `agent-harness.md` | Main Agent Loop, orchestration, model interaction, stop conditions. |
| `tool-system.md` | Built-in tools, tool schema, tool registry, tool execution, error handling. |
| `context-memory.md` | System prompt, project context, memory files, history compression, token control. |
| `permission-safety.md` | Permission mode, risky operations, user confirmation, rejection handling. |
| `skills-hooks-mcp.md` | Skills, hooks, MCP bridge, extension mechanism. |
| `java-spring-ai-implementation.md` | Java implementation, Spring AI integration, package structure, runtime flow. |

## Writing Rule

Each architecture document should include:

1. Purpose
2. Core flow
3. Key classes or functions
4. Important design details
5. Risks or limitations
6. Reference value for AI Secretary
