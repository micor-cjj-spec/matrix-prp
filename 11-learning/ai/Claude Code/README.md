# Claude Code

> 简称：cc  
> 源码地址：https://gitee.com/free/claude-code  
> 同步日期：2026-06-16

## 定位

`Claude Code/` 是 AI 学习模块下的独立学习目录，用于持续沉淀 Claude Code / cc 项目的学习计划、源码总结、架构拆解、运行记录和最终设计启发。

这个目录直接放在 `11-learning/ai/` 下，不再放到 `projects/` 目录中。后续所有与 Claude Code 相关的学习材料，都优先收敛到这个目录。

## 目录架构

```text
11-learning/ai/Claude Code/
├── README.md                 # 目录入口、学习索引、目录规则
├── learning-plan.md          # 阶段学习计划、阅读清单、下一步行动
├── source-summary.md         # 源码阅读总结、关键模块记录、稳定结论
├── architecture/
│   └── README.md             # 架构专题索引
├── notes/
│   └── README.md             # 临时阅读笔记、运行记录、问题记录
└── outputs/
    └── README.md             # 最终沉淀，可复用于 AI 秘书设计
```

## 目录设计原则

| 层级 | 用途 |
|---|---|
| `README.md` | 当前学习主题的入口，只放定位、目录说明、索引规则，不堆太多细节。 |
| `learning-plan.md` | 管理学习路径，包括先读什么、后读什么、当前完成到哪里。 |
| `source-summary.md` | 存放源码阅读后的稳定理解，例如模块职责、关键流程、重要类和函数。 |
| `architecture/` | 存放结构化架构拆解，例如 Agent Harness、工具系统、上下文、权限、MCP。 |
| `notes/` | 存放临时笔记、运行日志、问题记录、报错排查，后续可整理为正式总结。 |
| `outputs/` | 存放最终可复用结论，尤其是对 AI 秘书任务编排层、技能层、安全层的启发。 |

## 当前重点

| 方向 | 学习重点 |
|---|---|
| Agent Loop | 用户输入、模型推理、工具调用、工具结果回填、继续推理之间如何串起来。 |
| Agent Harness | Claude Code 编码助手的核心调度框架。 |
| Tool System | Bash、文件读写、搜索、任务、MCP 等工具如何注册、选择和执行。 |
| Context Management | 项目记忆、会话记忆、上下文压缩、Token 控制。 |
| Permission and Safety | 命令执行、文件修改、危险操作识别、用户确认。 |
| Skills / Hooks / MCP | 可扩展能力体系，可对照 AI 秘书 Skill 层设计。 |
| Java / Spring AI Implementation | 重点关注 Java 实现中如何组织 CLI、工具、模型调用和上下文。 |

## 与 AI 秘书项目的关系

| AI 秘书方向 | Claude Code 可参考内容 |
|---|---|
| 编排层 | Agent Loop、任务拆解、工具选择、执行状态管理。 |
| 任务层 | 任务创建、查询、更新、状态流转、后台执行。 |
| 技能层 | 工具注册、工具发现、参数校验、工具执行、MCP 桥接。 |
| 记忆系统 | 项目上下文、用户上下文、会话摘要、长期记忆。 |
| 安全系统 | 权限模式、危险命令检测、执行前确认、拒绝追踪。 |

## 文件命名规则

文件名统一使用英文 kebab-case，例如：

```text
learning-plan.md
source-summary.md
agent-harness.md
tool-system.md
context-memory.md
permission-safety.md
ai-secretary-reference.md
```

文件内容使用中文，方便长期阅读、复盘和迁移到自己的设计文档中。

## 后续扩展建议

当源码阅读深入后，`architecture/` 可以扩展为：

```text
architecture/
├── agent-harness.md
├── tool-system.md
├── context-memory.md
├── permission-safety.md
├── skills-hooks-mcp.md
└── java-spring-ai-implementation.md
```

`outputs/` 可以扩展为：

```text
outputs/
├── ai-secretary-reference.md
├── skill-layer-design-reference.md
├── orchestration-layer-design-reference.md
└── safety-design-reference.md
```

## 标签

`#AI` `#ClaudeCode` `#cc` `#Agent` `#CLI` `#SpringAI` `#MCP` `#Skill` `#AI秘书`
