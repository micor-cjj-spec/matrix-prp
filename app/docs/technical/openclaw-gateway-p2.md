# Matrix AI P2 — OpenClaw Gateway 安全任务接入（管理员预览）

## 当前边界

- PRP UI：「我的 → OpenClaw 任务工作台」，管理员独享。
- REST：`/api/ai/agent/capabilities`、`/tasks`、`/tasks/{id}`、`/tasks/{id}/approve`、`/tasks/{id}/cancel`。
- 创建任务只落库（`PENDING_APPROVAL`），**不会直接发往 OpenClaw**。审批需二次确认及后台枚举 `APPROVE_AGENT_TASK`，仅能批准一次。
- `PLAN`、`SUMMARIZE`、`ANALYZE` 三种文本型任务；其它类型拒绝。审批后后台线程发起一个 OpenClaw HTTP 调用，结果/失败状态留在 V10 表。每个任务由后端生成独立不可预测 UUID 及 `prp:{user}:{task_uuid}` 会话标识，不能由客户端覆盖，任务之间不共享上下文。
- 严禁上传凭据、生产数据库备份、私人健康或财务敏感记录。不会自动读取 PRP 业务数据库，Codex Worker 仍为 503（关闭）。
- 无 Gateway、无独立隔离确认或无 Token：只能创建待审批草稿，**不能执行**。前端“可用”仅表示配置完整，非在线检查。
- 单次请求最长 90 秒；失败状态标为 `FAILED`，无自动重试，避免外部可能已经处理的任务重复执行。重启时被中断的 `RUNNING` 任务不会自动重试，需要运维人工核查。
- **审批不是 Agent 沙盒**：用户输入的 `tool_choice:none` 与文本提示不能代替 OpenClaw 真实的 Agent 工具策略。

## 最重要：为什么不能接主 Gateway

OpenClaw 官方说明其 OpenAI Chat Completions HTTP endpoint 需要显式启用，使用共享 Token 时具有完整 owner/operator 权限，**不能**把普通的 Main Agent/Gateway Token 放给 Web 服务使用。即便将任务发送到某个 Agent，该令牌仍可能访问 Gateway 上其他高权限能力。

**生产必须为 PRP 创建独立 Gateway 实例/独立低权限系统用户与配置目录，使用独立 token，仅安装一个无工具权限的 `prp-planner` Agent。** 确保：
- `tools.deny`、Agent 专属 tool policy 和插件权限均拒绝 shell/exec、文件、浏览器、消息、网络工具、子 Agent、ACP 等可执行能力；禁用额外 skills/插件；由 OpenClaw 当前版本文档确认最终生效策略。
- 网关仅绑定 `127.0.0.1`；独立实例端口，如 18790。避免任何公网反向代理；Nginx 不得代理此 Gateway 端口。
- OS 进程与个人 OpenClaw 使用不同用户、凭据、文件目录、工作空间和权限。不能读取 Matrix PRP 数据、其他账户密钥、Docker socket、SSH 凭据或宿主重要目录。
- 网络策略阻断不必要的内网访问；模型调用额度在 OpenClaw 上单独限制与监控。
- 由于 PRP Gateway Token 是完整操作凭据，一旦泄露需要立即吊销轮换；存储于 Java systemd 安全环境，绝不放入 Web、Git、日志或 URL。
- 无法完成独立隔离与工具权限审计时保持 `MATRIX_PRP_OPENCLAW_ENABLED=false`。
- 以上限制需要运维配置与安全验收，**本次代码合并并不会自动创建受限实例**。

## 连接协议与配置（只在隔离实例验收后）

在隔离的 OpenClaw `openclaw.json` / JSON5 配置中开启：
```json5
{
  gateway: {
    http: { endpoints: { chatCompletions: { enabled: true } } }
  }
}
```

文档参考：https://docs.openclaw.ai/gateway/openai-http-api

独立 Gateway 的管理令牌配置于 OpenClaw 自身（`gateway.auth.mode=token`）。PRP 只在服务端环境读取：

```text
MATRIX_PRP_OPENCLAW_ENABLED=true
MATRIX_PRP_OPENCLAW_ISOLATION_CONFIRMED=true
MATRIX_PRP_OPENCLAW_GATEWAY_TOKEN=<gateway-secret>
MATRIX_PRP_OPENCLAW_PORT=18790
MATRIX_PRP_OPENCLAW_AGENT_ID=prp-planner
```

API 永远固定从 **Spring Boot Java 进程本机**访问 `http://127.0.0.1:<port>/v1/chat/completions`，禁止前端提供 host、URL、token、agent ID、session ID。默认 `18789` 仅用于代码配置回退；**请不要使用你现有高权限 Gateway 的端口和 Token**。未配置环境变量时默认全关闭。

## 生产数据与迁移步骤

1. 确认当前服务器的 Flyway 版本；没有完成 V8/V9 时按之前的 `safe-db-migrations-p0.md` 和 `ai-provider-settings-p1.md` 流程处理，旧库先备份并进行实际恢复演练。
2. V10 只新增 `prp_ai_agent_tasks`，不修改 V1～V9 SQL。使用已验证的 Flyway 增量 `migrate/validate`，不可重放旧 SQL，不可 `clean`、重建数据库或清空 Docker volume。
3. **先保持 OpenClaw 关闭并验证后端已有功能**，在隔离测试环境完成 Gateway 连接与单次审批实验（并验证任何 shell/文件/网络工具都不可能执行）。
4. 将 PRP 访问请求记录、审批记录、结果与系统日志纳入运维回归；验证管理员与普通用户 API 隔离、重复审批 409、任务取消、服务重启后的中断任务、视频/健康/推送及 DeepSeek 聊天兼容。
5. 无实机验收之前，不能将“配置完整”等同于安全或连接成功。

## P3/P4 边界

P3 可以围绕 **显式用户授权的 PRP 业务 API** 建立最小权限工具，不应直接给 OpenClaw 主机数据库凭据。P4 Codex Worker 需单独隔离执行、提交 PR 及人工审批。P2 不做任何实际服务器操作。

## 对齐官方文档

- https://docs.openclaw.ai/gateway/openai-http-api
- https://docs.openclaw.ai/gateway/security
