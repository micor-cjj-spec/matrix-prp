# GPT 零点击协作：GitHub Issue 自动请求入口

> **已验证状态（2026-11-22）**：协作代码经 [PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) 进入受保护 `main`。所有者已通过 [Issue #324](https://github.com/micor-cjj-spec/matrix-prp/issues/324) / [Actions #44995074733](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44995074733) 完成 V0→V1 一次性迁移，并真实验证并行领取、冲突拒绝、断点、交接、旧领取失效、所有者基于真实 Git 证据接管与释放（见 [#139](https://github.com/micor-cjj-spec/matrix-prp/issues/139)、[#145](https://github.com/micor-cjj-spec/matrix-prp/issues/145)）。最近核验的受保护状态 SHA 为 `6226ed6a706e20fe57e19a78c4b8119550996c1a`，需求 ACTIVE / Schema V1 / **version 10、9 个 READY、0 个占用、9 条成功写入记录**。App 非强制受保护分支 CAS 写入已有真实成功证据。历史断点修复 [PR #351](https://github.com/micor-cjj-spec/matrix-prp/pull/351) 已合并 `dev` 并通过 CI，但正式 Issue 入口仍运行 `main` 旧版代码；该回归场景尚未在正式入口验证。生产发布仍冻结。每次后续操作需重新读取实时版本。

关联需求：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)；[源代码 PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271)；[迁移提案 PR #144（已执行但未合并）](https://github.com/micor-cjj-spec/matrix-prp/pull/144)；[迁移请求 #324](https://github.com/micor-cjj-spec/matrix-prp/issues/324)；[验收 #139](https://github.com/micor-cjj-spec/matrix-prp/issues/139)。旧 Draft PR #138 是历史候选，不得再合并覆盖信任根。

## 用户体验与状态源

用户在 ChatGPT 中说“领取 T-001”“保存工作断点”“接管其他 GPT 会话”“执行已审核的 V0→V1 迁移”。在该会话 GitHub 连接可用的前提下，GPT 先读取受保护的 `prp-collab-state`，获取最新任务版本，然后通过 GitHub 连接，以仓库所有者身份创建标题为 `[PRP-COLLAB-REQUEST]` 的 Issue，请求体为严格 JSON。GitHub `issues.opened` 自动触发受保护 `main` 上的工作流。工作流会通过所有者身份、原始事件、实时 Issue 内容、只读源代码、状态版本、单仓库专用 App 和非强制 Git 推送检查，结果写回 Issue（不包含领取凭证）。

本方式**不需要每次点击 Run workflow 或 Required reviewers**；但它仍以 GitHub 所有者的请求为授权主体，并不能验证唯一的 ChatGPT 会话 ID。`worker_id` 只是标记。GitHub Issue 和状态分支均公开可读；不得提交敏感聊天内容、密码、PEM、Token、个人数据或把公开的 `claim_id` 当作保密认证因素。

## 一次性安装条件

- 在 GitHub 配置一个独立 Environment `prp-collab-automation`，**无 Required reviewers / Wait timer**，并将 Deployment branches 限制为 `main`。
- 在新 Environment 配置 `PRP_COLLAB_APP_PRIVATE_KEY` secret，并配置 `PRP_COLLAB_APP_CLIENT_ID`、`PRP_COLLAB_APP_ID=5561446`、`PRP_COLLAB_RULESET_ID=26294671` variables。无需将凭证提供给 ChatGPT。不要将这些 Secret 复制到公开 Issue。
- 保留现有 `prp-collab-controller` 人工审批 Environment，**不要直接把原环境解除审批来绕过安全控制**。
- 协作入口代码已通过 PR #271 受控集成到 `main`，并完成合并后 CI 与真实只读 `probe`。本入口不会移除 `app/deploy/publication-hold.json`，也不执行 PRP 应用生产部署。
- **迁移已于 2026-11-22 获得所有者明确授权并完成。** 首次写入时固定旧状态与提案 SHA、PR #144 非 Draft、App/Ruleset 单仓库边界和发布冻结均经真实 Actions 检查。方案 B 采用 owner-only 机器校验，**不代表已获得独立人类 reviewer 批准**（见 [Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147)）；手动 apply 的独立 reviewer 门槛仍保留。不得重放此次一次性迁移。

## 首次启用：不修改任务状态的只读探针

只读探针 **已于 2026-11-22 完成**（Issue #286 / Actions #44980594304），当时仅证明 Contents:read；随后迁移 #324 及真实 claim/takeover/release 才分别证明 Contents:write 和 CAS 写入链路。以下探针格式用于历史说明或再次只读核验，不构成新的写入授权。

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

**历史验收说明：**最初探针只验证 Issue → Actions → 专用 App 的只读权限；后续 Owner Issue #324 / Actions #44995074733 已完成固定 V0→V1 首次写入，随后多次独立请求成功。每次新状态变更仍需明确操作范围及实时状态版本。

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

`REQ-20261031-001` 已完成固定 V0→V1 迁移。以后登记新任务须实时读取 ACTIVE V1 快照、依赖和下一个连续任务 ID，并使用最新 `state.version`；多任务登记必须串行提交，不能复用旧版本。历史 V0 示例只用于追溯。

**正式入口已实现并通过真实写入验收：**`main` 上 owner Issue ingress 已完成迁移、claim、checkpoint、handoff、takeover、release 及预期拒绝测试；这不意味着九项开发任务 DONE。`dev` 的旧断点归档修复尚未进入正式 `main` 入口，不得声称释放后重新领取旧断点场景已在线上修复。

## 请求格式：一次性 V0 → V1 迁移

**以下是已执行的一次性迁移历史请求示例，不可重放。** 所有者采用方案 B 的 owner-authored `issues.opened` 身份校验（不强制独立 reviewer APPROVED，但会拒绝固定提案上的 CHANGES_REQUESTED）；旧手动 `workflow_dispatch` apply 仍强制合格的非所有者独立人类批准。2026-11-22 已通过 #324 完成所有者授权迁移；示例旧状态与提案 SHA 仅保留供审计。

```json
{
  "schema_version": 1,
  "action": "migrate_v1",
  "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "requirement_id": "REQ-20261031-001",
  "expected_state_sha": "062036f7021e215ffbfdcbf5689d207a0549b68b",
  "expected_proposal_sha": "bf80d5c384d5f687cb980b6e04127fc42167d7a8"
}
```

当时自动入口通过 GitHub 原始 `issues.opened` 事件确认作者与仓库所有者身份，并核验 PR #144 非 Draft、固定 V0/提案 SHA、单文件九任务差异、App 作用域、发布冻结与远端 CAS。**迁移已经执行成功，提案 PR #144 未合并；不允许重复执行。** owner-only 授权不等于独立人类审查，迁移本身也不会自动标记任务 DONE。

## 请求格式：创建并登记新任务（V1 之后）

新任务必须先创建独立的 GitHub Task Issue，再由一个 owner-authored `[PRP-COLLAB-REQUEST]` Issue 请求把它登记进受保护状态文件。两步都由 ChatGPT 使用已认证的仓库所有者连接执行；不能把“创建了 Issue”误报为“已登记”。

1. 先读取受保护状态，确认 Requirement 为 ACTIVE，且存在经固定 V0→V1 迁移建立的 T-006/#141、T-007/#142、T-008/#143、T-009/#146 四个任务身份；再读取最新 `state.version` 作为并发修订号及下一个连续任务 ID（例如 T-010）。**状态版本号会被领取、进度等操作递增，不能单独当作迁移完成证明。**
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
  "expected_version": 10,
  "issue_number": 151,
  "title": "Add dashboard filtering",
  "depends_on": ["T-009"],
  "allowed_paths": ["app/web/src/views/"]
}
```

把示例中的 Issue 编号、版本、ID、依赖和路径替换为本次读取/创建的真实值。协调器会重新从 GitHub API 读取 Task Issue，核对作者与请求作者均为仓库所有者、Issue 仍 open、标题完全匹配、清单字段逐项匹配；随后检查任务 ID 连续性、依赖存在性、Issue 编号唯一性和受限文件路径，最后通过非强制 Git CAS 写入一条 READY 任务。任务不会因登记而自动领取或启动。重复请求使用同一 UUID；不能通过复用 UUID 改写另一项操作。

普通任务的路径白名单只允许产品代码与非治理文档，不允许修改 `.github/workflows/**`、`app/scripts/dev-collab/**`、迁移/协调器信任根或部署文件。任务范围冲突由状态机拒绝。新登记须处于 ACTIVE V1，**迁移先决条件已满足**，但仍必须逐项核验 Task Issue、所有者身份、路径、依赖及实时版本。

## 限制与审计

**实际写入和审计已核验：**最初探针 #286 不证明写权限；owner-authored 迁移 #324 / Actions #44995074733 实际完成受保护状态 CAS 写入，后续 #330/#331、#336、#338、#347、#340/#341/#350 也有成功回执与远端状态证据，拒绝测试 #334/#339/#348 没有修改状态。最新快照是 V1 version 10、9 READY、0 claims。新操作仍需独立授权、准确版本和 SHA 核验。

非所有者请求、改写过的 Issue、非 `main` 来源、错误版本/凭证、额外 JSON 字段、重复操作碰撞和错误 Git SHA 都应失败关闭。权限不匹配时没有状态提交。不支持未经审查的 `accept`、`close` 或任意 Schema 修改。公开回执不写入认证 Token 或任何私密信息。
