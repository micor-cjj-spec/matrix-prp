# Claude Code（cc）学习跟踪

> 这是一次 PRP 学习模块同步记录，用于后续系统研究 Claude Code / cc 项目。

## 基本信息

| 字段 | 内容 |
|---|---|
| 项目名称 | Claude Code |
| 简称 | cc |
| 源码地址 | https://gitee.com/free/claude-code |
| 同步日期 | 2026-06-16 |
| 所属模块 | `11-learning/ai/` |
| 学习分类 | AI Agent、CLI 编码助手、Claude Code 架构、Spring AI、工具调用、MCP、技能系统 |
| 当前状态 | 已收录，待系统拆解 |
| 研究优先级 | P1：与 AI 秘书任务编排、工具调用、技能层设计高度相关 |

## 项目初步定位

这个 Gitee 项目围绕 Claude Code 展开，适合从“AI 编码助手 / Agent Harness / 工具调用框架”的角度研究。

公开 README 中看到的分支定位：

| 分支 | 初步说明 | 研究价值 |
|---|---|---|
| `main` | Claude Code Java：使用 Java + Spring AI 重写 Claude Code CLI AI 编码助手 | 重点研究 Java 后端实现、Spring AI 集成、工具系统、CLI 交互 |
| `claude` | Claude Code TypeScript 源码快照 | 适合对照原版架构、Agent Loop、工具协议、上下文管理 |
| `learn` | Learn Claude Code：拆解 Claude Code Agent Harness 架构的教学项目，包含渐进式课程 | 优先阅读，适合作为学习路线入口 |
| `buddy` | 公开页面显示存在该分支，具体内容待后续查看 | 待确认 |

## 为什么值得研究

该项目与当前 AI 秘书 / 任务中心 / 技能层设计有较强关联，重点价值在于：

1. **Agent Loop 设计**：研究 AI 如何从用户输入进入推理、工具选择、执行、结果回填、继续推理的循环。
2. **工具调用体系**：内置 Bash、文件读写、搜索、Web、任务管理、MCP 桥接等工具，可对照自己的 Skill 层设计。
3. **权限与安全机制**：适合学习命令执行、文件修改、危险操作识别、用户确认等机制。
4. **上下文管理**：包括项目级记忆、会话记忆、上下文压缩、Token 成本控制等能力。
5. **Skills / Hooks / MCP / Plugin**：这些模块可作为 AI 秘书后续能力扩展的参考。
6. **CLI 编码助手体验**：终端交互、斜杠命令、状态栏、流式输出、历史记录等设计可转化为产品体验参考。

## 与当前项目方向的关系

### 对 AI 秘书的参考价值

| 当前方向 | 可参考内容 |
|---|---|
| 任务编排层 | Agent Loop、任务拆解、工具选择、执行状态管理 |
| 任务层 | 后台任务创建、查询、更新、状态流转 |
| 技能层 | 工具注册、工具发现、参数校验、工具执行、MCP 桥接 |
| 安全控制 | 权限模式、危险命令检测、执行前确认、拒绝追踪 |
| 记忆系统 | `CLAUDE.md`、项目上下文、用户上下文、会话压缩 |
| 开发者助手 | 代码审查、Git 上下文、Commit 生成、Diff 渲染 |

### 对个人学习的参考价值

- 学习成熟 AI 编码助手的系统结构。
- 学习如何把“大模型调用”升级成“Agent 应用”。
- 学习 Java + Spring AI 场景下如何组织工具、命令、插件和上下文。
- 学习 CLI Agent 与 Web AI 助手在交互模式上的差异。

## 建议学习路线

### 第 0 阶段：项目收集与运行

目标：先跑起来，形成第一印象。

- [ ] 克隆源码：`git clone https://gitee.com/free/claude-code.git`
- [ ] 查看 `README.md`
- [ ] 查看 `BUILD.md`
- [ ] 查看 `需求文档.md`
- [ ] 切换并查看 `learn` 分支
- [ ] 切换并查看 `claude` 分支
- [ ] 记录能否成功编译运行

### 第 1 阶段：总览架构

目标：画出系统分层。

- [ ] 入口层：CLI 启动流程、命令解析、REPL 会话
- [ ] Agent 层：消息循环、模型调用、工具选择
- [ ] Tool 层：工具定义、注册、执行、结果回填
- [ ] Context 层：上下文加载、记忆文件、压缩策略
- [ ] Security 层：权限模式、危险操作识别、用户确认
- [ ] Extension 层：Skills、Hooks、MCP、Plugin

### 第 2 阶段：重点研究 Agent Harness

目标：理解 Claude Code 的核心运行机制。

重点问题：

1. 用户输入后，系统如何构造 Prompt / Message？
2. 模型返回工具调用时，如何解析和分发？
3. 工具执行结果如何进入下一轮上下文？
4. Agent Loop 的终止条件是什么？
5. 出错、拒绝、权限不足时如何恢复？
6. 子 Agent / 后台任务是否有独立状态？

### 第 3 阶段：研究工具系统与 Skill 层

目标：为自己的 AI 秘书 Skill 体系找参考。

重点问题：

1. 工具接口如何抽象？
2. 工具参数如何声明、校验和序列化？
3. 工具执行是同步还是异步？
4. 工具失败如何反馈给模型？
5. MCP 工具如何动态接入？
6. Skills 与 Commands、Tools 的边界是什么？

### 第 4 阶段：研究上下文与记忆

目标：为长期 AI 秘书设计记忆机制。

重点问题：

1. `CLAUDE.md` 的加载优先级如何设计？
2. 用户级、项目级、目录级记忆如何合并？
3. Token 超限前如何压缩？
4. 历史对话如何摘要？
5. 工具结果如何截断？
6. 哪些内容应该进入长期记忆，哪些只保留在短期上下文？

### 第 5 阶段：沉淀可复用设计

目标：把学习结果转化为自己的设计资产。

- [ ] 输出《Claude Code Agent Harness 架构拆解》
- [ ] 输出《Claude Code 工具调用体系拆解》
- [ ] 输出《Claude Code 权限与安全机制拆解》
- [ ] 输出《Claude Code 对 AI 秘书任务编排层的启发》
- [ ] 输出《AI 秘书 Skill 层改造建议》

## 后续产出文件建议

建议在 `11-learning/ai/projects/claude-code/` 下继续拆分：

```text
11-learning/ai/projects/claude-code/
├── 00-overview.md
├── 01-agent-harness.md
├── 02-tool-system.md
├── 03-context-memory.md
├── 04-permission-security.md
├── 05-skills-hooks-mcp-plugin.md
├── 06-java-spring-ai-implementation.md
└── 99-ai-secretary-reference.md
```

当前文件先作为收录入口和研究计划，后续深入阅读源码后再拆成专题文档。

## 标签

`#AI` `#ClaudeCode` `#cc` `#Agent` `#CLI` `#SpringAI` `#MCP` `#Skill` `#PRP` `#AI秘书`
