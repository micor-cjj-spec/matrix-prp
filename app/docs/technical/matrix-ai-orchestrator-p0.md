# Matrix AI Orchestrator P0 — DeepSeek Chat (V8 integrated)

## 当前实现与边界

- 固定四入口中的 **聊天** /chat 直接提供真实 Web/PWA 聊天界面。
- Spring Boot 通过 `/api/ai/chat/stream` 转发 DeepSeek SSE；API key 只放服务器环境变量，不发送给浏览器。
- 每个用户的会话、消息和用量独立存储，接口根据 JWT 的当前用户 ID 限定查询。
- `/api/ai/codex/capabilities` 仅管理员可见且始终禁用；`/api/ai/codex/jobs` 对管理员仍返回 503；**未执行 Codex/服务器命令**。
- H5 额外保留 `pages/ai/index` 访问入口；原生 uni-app App/小程序 streaming transport 尚未实现。
- 不自动开放健康、财务、文件、服务器工具给 AI；DeepSeek 仅接收用户输入和最近会话内容。

## 安全无损数据库升级（不可跳过）

1. **此 GitHub 合并并未触及生产数据库。** 先备份当前 `matrix_prp`、视频目录和 systemd 环境配置；在隔离数据库做恢复演练。
2. 所有已上线的旧库先核对 001～007，运行 `node app/scripts/verify-legacy-baseline.mjs`；确保 31 张既有表齐全、关键列和数据正常。
3. 尚未启用 Flyway 的旧数据库须在停写维护窗口 **显式执行 `baselineVersion=7`**，而且必须确认旧表全部与 V7 对应；绝不能使用 `baselineOnMigrate=true` 或 `clean`。详见 `safe-db-migrations-p0.md`。
4. 在 baseline 后执行 Flyway `migrate` + `validate`，只运行新增的 `V8__ai_orchestrator.sql`，不得重放 V1～V7。迁移新增三张 `prp_ai_*` 表，不修改历史 31 张表。已配置 Flyway 的库只需正常执行增量 V8。
5. 无 Flyway 迁移记录时 **不要**直接打开 `MATRIX_PRP_FLYWAY_ENABLED=true` 并重启现有 Java 服务。
6. 全新空库（不使用旧 Docker 初始化 SQL 路径）可由 Flyway 按 V1～V8 依次迁移。旧的 Docker 初始化目录只有 001～007，不能代替 V8。

## 系统配置

只在后端服务安全环境文件设置 `MATRIX_PRP_DEEPSEEK_API_KEY`。默认模型 `deepseek-chat`，可设 `MATRIX_PRP_DEEPSEEK_MODEL=deepseek-reasoner`。
默认额度：用户每月 200 次、全站 1000 次；预留估算 Token 用户每月 250000、全站 1000000。
可用 `MATRIX_PRP_AI_USER_MONTHLY_REQUESTS` 等配置降低限额。最大 4000 字提问、最多 12 条最近消息、最大 1024 输出 token。
配额是“保守预留”，不等于 DeepSeek 实际账单，更**不是美元硬预算**，需要在提供商设置预算与告警，并结合 Nginx 限流。

## 回归与安全检查

- GitHub CI 后端、Web/PWA、H5、真实 MySQL、Flyway V1～V8 迁移全部通过后方可合并。
- 管理员与普通用户交叉测试会话读取、非法 ID、无 JWT、限额耗尽与 Codex 拒绝。
- 生产启用前手工验证 DeepSeek 实际返回、iPhone Safari PWA、HTTPS/Nginx SSE 代理（关闭响应 buffering，并配置合理 read timeout）。
- 如遇线上异常，先停止写入并恢复已验证的备份；不要 `DROP DATABASE`、清空 Docker 卷或对未知迁移状态进行 Flyway repair。
