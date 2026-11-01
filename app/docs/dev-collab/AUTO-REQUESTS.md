# GPT 零点击协作：GitHub Issue 自动请求入口（Draft）

关联需求：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。代码和工作流仅存在于 [Draft PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)，**当前尚不能在生产状态分支调用**。

## 用户体验与状态源

用户在 ChatGPT 中说“领取 T-001”“保存工作断点”“接管其他 GPT 会话”“执行已审核的 V0→V1 迁移”。在该会话 GitHub 连接可用的前提下，GPT 先读取受保护的 `prp-collab-state`，获取最新任务版本，然后通过 GitHub 连接，以仓库所有者身份创建标题为 `[PRP-COLLAB-REQUEST]` 的 Issue，请求体为严格 JSON。GitHub `issues.opened` 自动触发受保护 `main` 上的工作流。工作流会通过所有者身份、原始事件、实时 Issue 内容、只读源代码、状态版本、单仓库专用 App 和非强制 Git 推送检查，结果写回 Issue（不包含领取凭证）。

本方式**不需要每次点击 Run workflow 或 Required reviewers**；但它仍以 GitHub 所有者的请求为授权主体，并不能验证唯一的 ChatGPT 会话 ID。`worker_id` 只是标记。GitHub Issue 和状态分支均公开可读；不得提交敏感聊天内容、密码、PEM、Token、个人数据或把公开的 `claim_id` 当作保密认证因素。

## 一次性安装条件

- 在 GitHub 配置一个独立 Environment `prp-collab-automation`，**无 Required reviewers / Wait timer**，并将 Deployment branches 限制为 `main`。
- 在新 Environment 配置 `PRP_COLLAB_APP_PRIVATE_KEY` secret，并配置 `PRP_COLLAB_APP_CLIENT_ID`、`PRP_COLLAB_APP_ID=5561446`、`PRP_COLLAB_RULESET_ID=26294671` variables。无需将凭证提供给 ChatGPT。不要将这些 Secret 复制到公开 Issue。
- 保留现有 `prp-collab-controller` 人工审批 Environment，**不要直接把原环境解除审批来绕过安全控制**。
- 必须先独立审核并单独批准将 Draft PR #138 合入受保护 `main`。当前仍有发布冻结 `app/deploy/publication-hold.json`；本入口不会移除冻结，也不执行 PRP 生产应用部署。
- 首次真实自动写入只在已审核的低影响测试任务上执行；保留远端 SHA、Issue 回执和 Actions 日志。没有真实审批配置、App Token 和 Ruleset 验证前不得宣称已上线。

## 首次启用：不修改任务状态的只读探针

在独立审查与一次性 Environment 配置完成、PR #138 获授权并合入 main 后，**优先运行以下只读探针**，不要直接领取 T-001 或迁移 V0。

由 ChatGPT GitHub 连接以仓库所有者身份创建标题严格为 `[PRP-COLLAB-REQUEST]` 的 Issue，正文仅包含：

```json
{
  "schema_version": 1,
  "action": "probe",
  "request_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "requirement_id": "REQ-20261031-001"
}
```

实际操作必须生成新的随机 UUID，不能在不同探针中重复使用示例值。探针只接受这四个字段，不允许传入任务编号、领取 ID、目标分支、迁移 SHA 或任意命令。

工作流先核验 owner-authored GitHub Issue、受保护 main 来源及发布冻结，再检查 GitHub App token 的安装仓库仅为 `micor-cjj-spec/matrix-prp`、状态分支保护和专用 Ruleset，最后读取当前远端状态 SHA 并发布脱敏回执。**不会提交 Git 变更，不会修改正式任务状态，不会触发生产部署。**

探针通过仅证明 Issue → Actions → 安装令牌签发与只读权限范围核验链路可用。它**不证明 Contents: write 权限或 Ruleset bypass 真实推送成功**。后续写入试点仍需明确授权和独立证据，不能把只读探针成功等同于整个零点击系统上线。

## 请求格式：任务领取

创建 GitHub Issue，标题必须**完全等于** `[PRP-COLLAB-REQUEST]`；正文仅为 JSON（不要 Markdown 代码围栏）。

```json
{
  "schema_version": 1,
  "action": "claim",
  "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "requirement_id": "REQ-20261031-001",
  "task_id": "T-001",
  "worker_id": "chat-example-001",
  "expected_version": 1
}
```

`request_id` 必须为本次操作新生成的 UUID；重试**相同操作**复用原 UUID。 `expected_version` 必须来自最新的受保护状态文件。其他变更操作（`start`、`progress`、`checkpoint`、`handoff`、`takeover`、`submit`、`rework`）受同一版本检查、原有状态机和领取校验约束。接管旧会话必须明确指定 `expected_claim_id`、目标 `new_worker_id`、当前版本和准确 Git SHA；没有断点时还须提供现存 Git 远端分支以证明可恢复的代码范围。任何仅凭“可能超时”发起的隐式抢占均不支持。

## 请求格式：无点击新增任务登记

新增任务采用两个 owner-authored Issue，均可由 ChatGPT GitHub 连接创建，不需要人工打开 Actions 或逐次审批：

1. 先创建普通任务 Issue，标题严格为 `[TASK][REQ-ID/T-NNN] 任务标题`，正文包含目标、验收、依赖和范围，并在末尾加入唯一的机器清单：

   ```html
   <!-- PRP_TASK_MANIFEST
   {"schema_version":1,"requirement_id":"REQ-20261031-001","task_id":"T-010","title":"增加任务看板筛选","depends_on":[],"allowed_paths":["app/web/src/"]}
   -->
   ```

2. 再创建标题为 `[PRP-COLLAB-REQUEST]` 的请求 Issue，正文仅为以下 JSON。将 `issue_number` 替换为刚创建的任务 Issue 编号，并使用读取到的最新状态版本。

   ```json
   {
     "schema_version": 1,
     "action": "register_task",
     "request_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
     "requirement_id": "REQ-20261031-001",
     "task_id": "T-010",
     "worker_id": "chat-example-001",
     "expected_version": 1,
     "issue_number": 151,
     "title": "增加任务看板筛选",
     "depends_on": [],
     "allowed_paths": ["app/web/src/"]
   }
   ```

工作流会核对任务 Issue 与请求清单的作者、Issue 编号、标题、依赖及范围是否完全一致；只允许登记下一个连续任务编号、未重复使用的 Issue 编号和已存在的依赖任务。登记成功后任务状态为 `READY`，不会自动领取；随后 ChatGPT 再发起一次 `claim` 请求。

普通任务的路径范围采用白名单：`app/backend/src/main/java/`、`app/backend/src/test/java/`、`app/web/src/`、`app/mobile/src/`，以及非协作治理文档目录（`app/docs/ai-notes/`、`api/`、`bugs/`、`data/`、`decisions/`、`features/`、`product/`、`releases/`、`technical/`、`README.md`）。GitHub Actions 工作流、协作协调器、部署配置、后端资源配置和数据库迁移不属于普通任务范围，必须单独做治理审查。

对当前 `REQ-20261031-001`，必须先完成固定 V0→V1 迁移，之后才能登记新任务；当前 V0 不会因创建任务 Issue 而被修改。多任务创建按最新状态版本逐项登记，不能并发复用同一版本。

**当前仍是 Draft 候选实现**：PR #138 完成独立审查、获得合并授权并配置一次性 Environment 后，可先在 **V0 保持不变** 的情况下执行只读 `probe` 真实 Issue 事件验收；只有执行新任务登记等 V1 操作时，才需要事先完成明确授权的固定 V0→V1 迁移。

## 请求格式：一次性 V0 → V1 迁移

只有当 `prp-collab-state` **仍处于指定 V0 SHA** 且提案分支仍处于审核过的 SHA，才允许执行以下严格固定的唯一迁移：

```json
{
  "schema_version": 1,
  "action": "migrate_v1",
  "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "requirement_id": "REQ-20261031-001",
  "expected_state_sha": "062036f7021e215ffbfdcbf5689d207a0549b68b",
  "expected_proposal_sha": "fb57656dca6df5f12e083fc0430263b4d88e452d"
}
```

这一请求通过 GitHub 原始 `issues.opened` 事件确认作者是仓库所有者，作为此次唯一结构迁移的明确授权，**不用再到 GitHub 点击 approve**。程序仍需要检查 PR #144 的身份、单文件变更、九任务精确内容、未修改的原任务状态与领取记录、专用 App 单仓库作用域、当前 main 发布冻结、源 SHA、并发和远端写入结果。它不会提供任意版本迁移接口，也不会自动将 Draft PR #144 合并或标记 DONE。

## 请求格式：创建并登记新任务（V1 之后）

新任务必须先创建独立的 GitHub Task Issue，再由一个 owner-authored `[PRP-COLLAB-REQUEST]` Issue 请求把它登记进受保护状态文件。两步都由 ChatGPT 使用已认证的仓库所有者连接执行；不能把“创建了 Issue”误报为“已登记”。

1. 先读取受保护状态，确认 Requirement 为 ACTIVE、版本为 V1 或更高，并读取下一个连续任务 ID（例如 T-010）。
2. 创建 Task Issue，标题必须为 `[TASK][REQ-20261031-001/T-010] Add dashboard filtering`。正文包含目标/验收说明，并且**恰好包含一次**以下机器清单（JSON 字段不能增删）：

```html
<!-- PRP_TASK_MANIFEST
{"schema_version":1,"requirement_id":"REQ-20261031-001","task_id":"T-010","title":"Add dashboard filtering","depends_on":["T-009"],"allowed_paths":["app/web/src/views/"]}
-->
```

3. 再创建请求 Issue，标题为 `[PRP-COLLAB-REQUEST]`，正文例如：

```json
{
  "schema_version": 1,
  "action": "register_task",
  "request_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  "requirement_id": "REQ-20261031-001",
  "task_id": "T-010",
  "worker_id": "chat-new",
  "expected_version": 9,
  "issue_number": 151,
  "title": "Add dashboard filtering",
  "depends_on": ["T-009"],
  "allowed_paths": ["app/web/src/views/"]
}
```

把示例中的 Issue 编号、版本、ID、依赖和路径替换为本次读取/创建的真实值。协调器会重新从 GitHub API 读取 Task Issue，核对作者与请求作者均为仓库所有者、Issue 仍 open、标题完全匹配、清单字段逐项匹配；随后检查任务 ID 连续性、依赖存在性、Issue 编号唯一性和受限文件路径，最后通过非强制 Git CAS 写入一条 READY 任务。任务不会因登记而自动领取或启动。重复请求使用同一 UUID；不能通过复用 UUID 改写另一项操作。

普通任务的路径白名单仅允许产品代码与文档目录，不允许修改 `.github/workflows/**`、`app/scripts/dev-collab/**`、迁移/协调器信任根或部署文件。任务之间的重叠范围由状态机拒绝。新任务登记仅在该需求完成受审查的 V0→V1 迁移后开放；V0 状态不接受注册。

## 限制与审计

当前 GitHub 连接能创建 owner-authored Issues，但未提供直接 `workflow_dispatch` 接口；选择 Issue 事件是为了避免 GUI。**GitHub Actions 是否确实响应此连接所创建的 Issue，尚需上线后真实验收**。GitHub 事件可能延迟；创建 Issue 不代表写入已完成。ChatGPT 必须读取关联 Actions 和原 Issue 的回执以及受保护状态 SHA，才能汇报成功。

非所有者请求、改写过的 Issue、非 `main` 来源、错误版本/凭证、额外 JSON 字段、重复操作碰撞和错误 Git SHA 都应失败关闭。权限不匹配时没有状态提交。不支持未经审查的 `accept`、`close` 或任意 Schema 修改。公开回执不写入认证 Token 或任何私密信息。
