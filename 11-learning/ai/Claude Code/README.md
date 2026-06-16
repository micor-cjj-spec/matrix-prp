# Claude Code

> Short name: cc  
> Source: https://gitee.com/free/claude-code  
> Sync date: 2026-06-16

## Positioning

Claude Code is an independent study topic under the AI learning module. This directory is used to continuously organize learning plans, source-code summaries, architecture notes, running notes, and reusable conclusions related to Claude Code / cc.

This directory should stay directly under `11-learning/ai/` and should not be placed under `projects/`.

## Directory Architecture

```text
11-learning/ai/Claude Code/
├── README.md                 # Directory entrance and study index
├── learning-plan.md          # Stage plan, reading checklist, next actions
├── source-summary.md         # Source-code reading summary and key module notes
├── architecture/
│   └── README.md             # Architecture topic index
├── notes/
│   └── README.md             # Daily reading notes, issues, commands, experiments
└── outputs/
    └── README.md             # Final reusable conclusions and design references
```

## Why This Structure

| Layer | Purpose |
|---|---|
| `README.md` | Acts as the entrance of the Claude Code study topic. It should not carry too many details. |
| `learning-plan.md` | Tracks what to learn, in what order, and what is already done. |
| `source-summary.md` | Stores stable source-code understanding, module summaries, and important class/function notes. |
| `architecture/` | Stores deeper architecture breakdowns such as Agent Harness, tool system, memory, permission, and MCP. |
| `notes/` | Stores temporary reading notes, running logs, questions, and troubleshooting records. |
| `outputs/` | Stores reusable conclusions that can be migrated into AI Secretary design documents. |

## Current Focus

| Area | Study Focus |
|---|---|
| Agent Loop | How user input, model reasoning, tool calls, tool results, and next-round reasoning are connected. |
| Agent Harness | The core orchestration framework of the Claude Code coding assistant. |
| Tool System | How Bash, file operations, search, task, MCP, and other tools are registered and executed. |
| Context Management | Project memory, session memory, context compression, and token control. |
| Permission and Safety | Command execution, file modification, dangerous operation detection, and user confirmation. |
| Skills / Hooks / MCP | Extension model that can be compared with the AI Secretary Skill layer. |
| Java / Spring AI Implementation | Focus on how the Java implementation organizes CLI, tools, model calls, and context. |

## Relationship with AI Secretary

| AI Secretary Area | Reference Value from Claude Code |
|---|---|
| Orchestration Layer | Agent Loop, task decomposition, tool selection, execution state management. |
| Task Layer | Task creation, query, update, status transition, background execution. |
| Skill Layer | Tool registration, tool discovery, parameter validation, tool execution, MCP bridge. |
| Memory System | Project context, user context, session summary, long-term memory. |
| Safety System | Permission mode, dangerous command detection, confirmation before execution, rejection tracking. |

## File Naming Rule

All file names in this directory should use English kebab-case, for example:

```text
learning-plan.md
source-summary.md
agent-harness.md
tool-system.md
context-memory.md
permission-safety.md
ai-secretary-reference.md
```

The document content can be written in Chinese, but file names should remain English for long-term maintainability.

## Future Expansion

When source reading becomes deeper, the `architecture/` directory can be expanded like this:

```text
architecture/
├── agent-harness.md
├── tool-system.md
├── context-memory.md
├── permission-safety.md
├── skills-hooks-mcp.md
└── java-spring-ai-implementation.md
```

The `outputs/` directory can later contain:

```text
outputs/
├── ai-secretary-reference.md
├── skill-layer-design-reference.md
└── orchestration-layer-design-reference.md
```

## Tags

`#AI` `#ClaudeCode` `#cc` `#Agent` `#CLI` `#SpringAI` `#MCP` `#Skill` `#AISecretary`
