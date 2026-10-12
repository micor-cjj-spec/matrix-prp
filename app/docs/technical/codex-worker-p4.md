# Matrix AI P4 — 管理员审批的 Codex GitHub Actions Worker

## 范围与安全选择

目标流程：Matrix PRP 管理员创建 FIX / IMPLEMENT / TESTS 草稿 → 逐项批准 → 后端通过 GitHub Actions Workflow Dispatch API 派发任务 → **GitHub-hosted 临时 Runner** 调用 `openai/codex-action@v1` → 限定工作区源码修改 → 后端/前端/移动端测试 → 分离的高权限作业只接收校验过的 patch → 创建 `codex/prp-<task-uuid>` 分支和 **待人工审核 PR**。

不在生产服务器直接运行 Codex CLI。PRP 的 Spring Boot Java 进程不执行命令，不接收任意 shell/URL/仓库/分支参数，不把 GitHub Token、OpenAI API Key 发送到浏览器。OpenClaw Gateway 仍为 P2 低权限文本方案，不能代替 Codex 或对 GitHub 授权。

适用仓库固定为 **`micor-cjj-spec/matrix-prp`**（P4 仅此仓库）。任务只接受 `IMPLEMENT`、`FIX`、`TESTS` 三类，1～1500 字符。不可发起数据库操作、系统部署、任意脚本或任意仓库工作。普通用户不可查看任务、审批或发起任务。

## 关键权限隔离

1. `develop` job：GitHub-hosted `ubuntu-latest`，`contents: read`，`checkout persist-credentials:false`，Codex Action `permission-profile:":workspace"`、`safety-strategy: drop-sudo`；GitHub 写 Token **不暴露给 Codex**。依赖下载在 Codex 运行前完成；允许模型在工作区源码目录完成受限代码改动。
2. 代码改动限制为 `app/backend/src/main/java/`、`app/backend/src/test/java/`、`app/web/src/`、`app/mobile/src/`，30 个以内，禁止 symlink、二进制文件、数据库迁移、配置、`.github` 工作流、Docker、部署、Git 操作。限补丁体积，先做静态检查，再通过后端测试、Web/Vite build 和 Mobile H5 构建。
3. `publish` job：只有 develop **完全成功**才能运行；单独的 GitHub-hosted Runner 获得 `contents: write` 与 `pull-requests: write`。只下载补丁，`git apply --check`、再校验文件路径与 Git index 类型，关闭 Git hooks；**不运行补丁内可执行代码或测试脚本**。推送新分支并调用 `gh pr create`。失败即保留日志、不合并、不部署。
4. `on: workflow_dispatch` 是唯一触发方式；禁止 `pull_request_target` 和复用生产 self-hosted runner。每个任务 UUID 映射一个分支和 workflow run-name，重复审批通过 DB 原子 `claim` 禁止；任何网络异常都标记 `DISPATCH_UNCERTAIN` 且不会自动重试，需人工在 GitHub Actions 检查是否已运行。
5. 若 PR 分支测试不通过，不创建 PR。GitHub Repo 设置若未开启 Allow GitHub Actions to create and approve pull requests，发布任务可能失败，不能绕过审批直接部署。
6. Codex **可能修改不可信源代码并执行测试**，因此不可向 agent 作业开放云服务器秘钥、数据库、Docker socket、生产内网或持久性主机。GitHub-hosted Runner 是 P4 选用的隔离边界；不能以生产服务器持久 Runner 代替。

## API 与状态

- `GET /api/ai/codex/requests/capabilities`：是否具备派发条件（只表示配置完整，不等于真实运行验收）。
- `POST /api/ai/codex/requests`：仅创建草稿（即使 Codex 关闭也可创建）。
- `POST /api/ai/codex/requests/{id}/approve`：需管理员身份及 `confirmation=APPROVE_CODEX_JOB`；前端还有单独确认对话框。
- `POST /api/ai/codex/requests/{id}/cancel`：仅待审批可取消。
- `GET /api/ai/codex/requests`：最近 50 条当前管理员的任务记录；`GET /api/ai/codex/requests/{id}`：按 UUID 查询 GitHub Actions 运行/PR 链接（实时状态只读查询，可能延迟，取最近 100 个运行）。
- DB 状态是 `PENDING_APPROVAL` → `DISPATCHING` → `DISPATCHED` 或 `FAILED`；`CANCELLED` 只从待审取消。`DISPATCHED` 仅表示 GitHub 接受调度，**不表示 Codex 完成、PR 已生成或测试通过**。以 GitHub Actions 官方运行状态和实际 PR 为准。
- 旧接口 `POST /api/ai/codex/jobs` 保持禁用/503，避免早期客户端绕过审批。P2 OpenClaw / P3 用户上下文授权不变。

## 生产准备与启用前置步骤

1. **不直接在生产使用本次 GitHub 合并后的数据库迁移**。先离线备份/实际恢复演练 `matrix_prp`，确认 V8～V10 已按版本迁移，然后通过 Flyway **只追加 V11** 的 `prp_ai_codex_jobs` 表；不要打开未知旧库的自动 baseline、重放历史 SQL 或删除卷。参见 `safe-db-migrations-p0.md`。
2. 在私有 GitHub 仓库中安全保存独立的 `PRP_CODEX_OPENAI_API_KEY` Actions Secret（OpenAI API 单独计费，ChatGPT 订阅不提供它）。该密钥由 Codex Action 代理使用，必须设置模型预算和告警。实际权限控制以官方 GitHub Action 和 Runner 的版本为准。
3. 为 PRP 的后端创建 **专用短期、最小权限 GitHub token**，仅允许此私有仓库 `Actions: write`（Workflow Dispatch）和必要的读取工作流元数据；不要授予仓库广泛管理/contents write 权限。Token **只**保存在 Java systemd 的受保护环境文件中，不能提交到仓库。
4. 在 GitHub Settings → Actions → General 检查 `GITHUB_TOKEN` 的工作流写权限、允许工作流创建 PR 的策略；仅授权可信管理员调度。确认仓库能访问 GitHub-hosted Linux Runner，和 OpenAI API Secret 对应的项目余额。
5. 在完成所有环境安全检查后，后台环境设置（示意，**切勿将真实 token 写入 Git**）：

   ```text
   MATRIX_PRP_CODEX_ENABLED=true
   MATRIX_PRP_CODEX_GITHUB_TOKEN=<scoped-actions-dispatch-token>
   MATRIX_PRP_CODEX_REPOSITORY=micor-cjj-spec/matrix-prp
   ```

6. 在预生产环境创建无敏感信息的测试 FIX 任务、点击批准，观察 `PRP-CODEX-<id>` Actions 运行、测试、PR 创建和后台回显链接。必须验证非管理员 403、重复批准 409、未启用时 503、GitHub 故障后不重复派发、没有 diff 或检测到非允许目录时失败。
7. 本次 PR 只合并代码，不会运行任何 `workflow_dispatch`、不在服务器配置密钥、不运行 Codex，不部署前端或生产 API。

## 运行限制和待完善方向

- 单工作流设置 35 分钟 Runner 超时 + 8 分钟发布超时，GitHub Actions/模型可能收费；初版没有通用取消 GitHub workflow 的能力，UI 的取消只适用于未批准草稿。
- GitHub Workflow Dispatch API 返回 HTTP 204 而不是运行 ID；后台通过唯一 run-name 列表近似关联，任务大量积压时超过最近 100 条则旧任务可能显示为“未找到运行记录”。这不应触发重复执行。
- P4 是**受控 PR 生产线而非任意本机 Codex shell**，不将当前手机端 DeepSeek/Kimi 聊天请求自动升级成代码执行。
- 外部 prompt、代码文件和构建依赖都视为潜在不可信内容。即使有代码路径校验、最小权限和临时 Runner，仍需管理员对每个 PR 做代码审查及供应链检查。
- 第一版不提供跨仓库支持、不自动合并、不自动部署、不访问生产 MySQL、不接管现有用户级 OpenClaw 的权限。

参考：https://github.com/openai/codex-action 和 https://docs.github.com/en/rest/actions/workflows
