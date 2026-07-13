# Claude Code Architecture

> 本目录用于存放 Claude Code 源码阅读后的结构化架构拆解。

## 用途

`architecture/` 目录用于把 Claude Code 拆成稳定的架构专题。这里的内容应该比 `notes/` 更正式、更结构化，能够作为后续复盘和设计参考。

## 规划文件

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

## 专题范围

| 文件 | 范围 |
|---|---|
| `agent-harness.md` | 主 Agent Loop、编排流程、模型交互、终止条件。 |
| `tool-system.md` | 内置工具、工具 Schema、工具注册、工具执行、异常处理。 |
| `context-memory.md` | 系统提示词、项目上下文、记忆文件、历史压缩、Token 控制。 |
| `permission-safety.md` | 权限模式、危险操作、用户确认、拒绝处理。 |
| `skills-hooks-mcp.md` | Skills、Hooks、MCP 桥接、扩展机制。 |
| `java-spring-ai-implementation.md` | Java 实现、Spring AI 集成、包结构、运行流程。 |

## 写作规则

每个架构文档建议包含：

1. 研究目标
2. 核心流程
3. 关键类或函数
4. 重要设计细节
5. 风险或限制
6. 对 AI 秘书的参考价值

## 当前状态

待源码阅读后补充具体专题文档。
