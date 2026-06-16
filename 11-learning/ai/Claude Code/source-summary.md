# Claude Code Source Summary

> This document stores stable source-code reading conclusions. Temporary notes should go to `notes/`; structured architecture breakdowns should go to `architecture/`.

## Reading Status

| Item | Status | Notes |
|---|---|---|
| Repository collected | Done | Source: https://gitee.com/free/claude-code |
| Local clone | Todo | Pending local operation |
| Local build | Todo | Pending verification |
| Local run | Todo | Pending verification |
| Main branch overview | Todo | Focus on Java / Spring AI implementation |
| Learn branch overview | Todo | Focus on Agent Harness teaching materials |
| Claude branch overview | Todo | Focus on original TypeScript source snapshot |

## Project Positioning

Claude Code / cc should be studied as an AI coding-agent system rather than a normal CLI tool. The key is not only how it sends prompts to a model, but how it organizes a continuous agent loop with tools, context, permissions, and extensions.

## High-Level Architecture Hypothesis

```text
User Input
   ↓
CLI / Command Layer
   ↓
Agent Loop / Orchestration
   ↓
Model Call
   ↓
Tool Call Decision
   ↓
Tool Execution
   ↓
Tool Result Back to Context
   ↓
Continue / Finish
```

This is a hypothesis before deep source reading. It should be corrected after reading concrete implementation classes, functions, and modules.

## Key Modules to Identify

| Module | What to Find |
|---|---|
| CLI entry | Startup class, command parser, interactive loop |
| Model client | Model provider abstraction, request/response mapping, streaming handling |
| Agent loop | Main reasoning loop, stop condition, retry strategy |
| Tool registry | Tool definition, parameter schema, registration, discovery |
| Tool executor | Execution flow, error handling, timeout, result formatting |
| Context builder | System prompt, user message, project memory, conversation history |
| Memory manager | Project memory file, session summary, compression |
| Permission manager | User confirmation, allow/deny rules, risky operation detection |
| MCP bridge | External tool discovery and invocation |
| Skill system | Skill loading, matching, execution boundary |

## Source Reading Template

For each important class, function, or module, use the following format:

```text
### Module / Class / Function Name

Path:

Responsibility:

Input:

Output:

Key Flow:

Important Details:

Reference for AI Secretary:
```

## Initial Research Questions

1. What is the real entry point of the Java implementation?
2. How does the project abstract model providers?
3. How does it represent messages and tool calls?
4. How does it register built-in tools?
5. How does it parse tool calls from model responses?
6. How does it control command execution permission?
7. How does it load project memory files?
8. How does it support MCP and external extensions?
9. What parts can be reused in AI Secretary orchestration?
10. What parts should not be reused directly?

## Reusable Conclusions

Pending source reading.
