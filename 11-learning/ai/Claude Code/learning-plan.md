# Claude Code Learning Plan

> Goal: systematically study Claude Code / cc, including its architecture, tool calling, context management, permission control, extension model, and reusable design value for the AI Secretary project.

## Basic Information

| Field | Value |
|---|---|
| Project name | Claude Code |
| Short name | cc |
| Source | https://gitee.com/free/claude-code |
| Module | `11-learning/ai/Claude Code/` |
| Status | Collected, pending systematic source reading |
| Priority | P1 |

## Stage 0: Collect and Run

Goal: run the project first and identify branches, build process, and main entry points.

- [ ] Clone source: `git clone https://gitee.com/free/claude-code.git`
- [ ] Read `README.md`
- [ ] Read `BUILD.md`
- [ ] Read requirement or design documents if available
- [ ] Check `main` branch
- [ ] Check `learn` branch
- [ ] Check `claude` branch
- [ ] Record whether local build succeeds
- [ ] Record whether local runtime succeeds
- [ ] Record errors and solutions during setup

## Stage 1: Architecture Overview

Goal: draw the first system map of Claude Code as a CLI Agent.

- [ ] Entry layer: CLI startup, command parsing, REPL session
- [ ] Agent layer: message loop, model call, tool selection
- [ ] Tool layer: tool definition, registration, execution, result return
- [ ] Context layer: context loading, memory files, compression policy
- [ ] Security layer: permission mode, dangerous operation detection, confirmation
- [ ] Extension layer: Skills, Hooks, MCP, Plugin

## Stage 2: Agent Harness

Goal: understand the core runtime mechanism of Claude Code.

Key questions:

1. How is the prompt or message list built after user input?
2. How does the system parse and dispatch tool calls returned by the model?
3. How are tool execution results inserted back into context?
4. What are the stop conditions of the Agent Loop?
5. How does the system recover from errors, rejections, or permission failures?
6. Does the project support sub-agents or background tasks with independent state?

## Stage 3: Tool System and Skill Layer

Goal: extract references for the AI Secretary Skill layer.

Key questions:

1. How is a tool interface abstracted?
2. How are tool parameters declared, validated, and serialized?
3. Are tool executions synchronous or asynchronous?
4. How are tool failures returned to the model?
5. How are MCP tools dynamically connected?
6. What is the boundary between Skills, Commands, and Tools?

## Stage 4: Context and Memory

Goal: extract references for long-term AI Secretary memory design.

Key questions:

1. How are project-level memory files loaded?
2. How are user-level, project-level, and directory-level memories merged?
3. How does the system compress context before token overflow?
4. How are historical conversations summarized?
5. How are large tool results truncated?
6. Which information should become long-term memory, and which should remain short-term context?

## Stage 5: Permission and Safety

Goal: understand safety mechanisms around command execution and file modification.

Key questions:

1. How does the system classify safe and risky operations?
2. Which operations require confirmation?
3. How are user decisions recorded?
4. How does the system prevent accidental destructive commands?
5. How can this safety model be reused in AI Secretary tools?

## Stage 6: Reusable Outputs

Goal: transform source reading into design assets.

- [ ] Output Agent Harness breakdown
- [ ] Output tool system breakdown
- [ ] Output context and memory breakdown
- [ ] Output permission and safety breakdown
- [ ] Output AI Secretary orchestration reference
- [ ] Output AI Secretary Skill layer improvement proposal

## Next Actions

- [ ] Open the Gitee repository locally
- [ ] Start from the `learn` branch
- [ ] Compare the `main` Java implementation with the `claude` source snapshot
- [ ] Fill `source-summary.md` after the first source reading round
- [ ] Move stable conclusions into `architecture/` and `outputs/`
