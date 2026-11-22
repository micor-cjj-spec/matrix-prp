# GPT 零点击协作：GitHub Issue 自动请求入口

> **当前状态（2026-11-22）**：受控协作代码已由 [PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) 合并到受保护 `main`，合并后 CI 34/34 成功。[Owner 只读请求 Issue #286](https://github.com/micor-cjj-spec/matrix-prp/issues/286) / [Actions #44980594304](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44980594304) 已通过，返回脱敏回执，正式 `prp-collab-state` 保持 V0 固定 SHA `062036f7021e215ffbfdcbf5689d207a0549b68b`。**这仅验证 App Contents:read 链路，不代表 Contents:write 与受保护状态分支写入已验收；PR #144 仍为 Draft，生产发布仍冻结。**

关联需求：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)；[已合并源代码 PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271)；[待迁移提案 PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)。旧 PR #138 仍保留为 Draft 历史候选，不可直接再次合并覆盖安全修复。

## 用户体验与状态源

用户在 ChatGPT 中说“领取 T-001”“保存工作断点”“接管其他 GPT 会话”“执行已审核的 V0→V1 迁移”。在该会话 GitHub 连接可用的前提下，GPT 先读取受保护的 `prp-collab-state`，获取最新任务版本，然后通过 GitHub 连接，以仓库所有者身份创建标题为 `[PRP-COLLAB-REQUEST]` 的 Issue，请求体为严格 JSON。GitHub `issues.opened` 自动触发受保护 `main` 上的工作流。工作流会通过所有者身份、原始事件、实时 Issue 内容、只读源代码、状态版本、单仓库专用 App 和非强制 Git 推送检查，结果写回 Issue（不包含领取凭证）。

本方式**不需要每次点击 Run workflow 或 Required reviewers**；但它仍以 GitHub 所有者的请求为授权主体，并不能验证唯一的 ChatGPT 会话 ID。`worker_id` 只是标记。GitHub Issue 和状态分支均公开可读；不得提交敏感聊天内容、密码、PEM、Token、个人数据或把公开的 `claim_id` 当作保密认证因素。

## 一次性安装条件

- 在 GitHub 配置一个独立 Environment `prp-collab-automation`，**无 Required reviewers / Wait timer**，并将 Deployment branches 限制为 `main`。
- 在新 Environment 配置 `PRP_COLLAB_APP_PRIVATE_KEY` secret，并配置 `PRP_COLLAB_APP_CLIENT_ID`、`PRP_COLLAB_APP_ID=5561446`、`PRP_COLLAB_RULESET_ID=26294671` variables。无需将凭证提供给 ChatGPT。不要将这些 Secret 复制到公开 Issue。
- 保留现有 `prp-collab-controller` 人工审批 Environment，**不要直接把原环境解除审批来绕过安全控制**。
- 协作入口代码已通过 PR #271 受控集成到 `main`，并完成合并后 CI 与真实只读 `probe`。本入口不会移除 `app/deploy/publication-hold.json`，也不执行 PRP 应用生产部署。
- 正式 V0 的首次写入只允许用户单独明确授权的固定 V0→V1 迁移，不能先领取测试任务。PR #144 必须非 Draft，所有 SHA / delta / Ruleset / App 单仓库边界均须通过。独立 reviewer 是否为自动 owner Issue 的额外强制条件仍在 [Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147) 做治理决议；不能把当前 owner-only 代码路径说成独立审查已通过。

## 首次启用：不修改任务状态的只读探针

只读探针 **已于 2026-11-22 实际完成**（Issue #286、Actions #44980594304），并核对远端 V0 状态 SHA 未变。以下保留请求格式以供后续独立只读复验参考；不得从探针通过推断写入或迁移授权。

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

探针通过仅证明 Issue → Actions → 安装令牌签发与只读权限范围核验链路可用。它**不证明 Contents: write 权限或 Ruleset bypass 真实推送成功**。后续首个正式写入试点是单独授权且独立审核的固定 V0→V1 迁移，不能把只读探针成功等同于整个零点击系统上线。

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

**当前实现已在 `main`，但真实状态写入尚未启用验收。** V0 不允许 claim / register_task 等常规写入；只有一次性固定迁移经过单独授权和完整安全门控后，才可验证写入链路。

## 请求格式：一次性 V0 → V1 迁移

仅在用户**明确授权此次固定 V0→V1 迁移**、旧状态及候选 SHA 仍为下面的精确值、PR #144 非 Draft 且经治理模式确认后，才能创建最终 `migrate_v1` 请求。当前代码分为两条路径：**owner-authored `issues.opened`** 使用经过 GitHub 事件/Issue 身份核验的所有者特例，拒绝当前 SHA 的 `CHANGES_REQUESTED`，但**不强制独立 reviewer APPROVED**；**旧手动 `workflow_dispatch` apply** 强制当前 SHA 的非所有者、非作者、人类 `COLLABORATOR`/`MEMBER` reviewer 批准。前者是单人授权，不等于独立审查。是否为自动路径额外要求一次性独立审核，须先在 [Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147) 明确，不得未经治理决定直接启动真实写入。普通“继续”不等于迁移授权：

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

上述自动入口通过 GitHub 原始 `issues.opened` 事件确认作者与仓库所有者身份，**不要求用户另行点击 GitHub Actions 审批**；程序仍核验 PR #144 身份、非 Draft、拒绝精确提案 SHA 上的反对审查、固定旧/新 SHA、单文件九任务精确差异、未修改的任务状态和账本、专用 App 单仓库作用域、主分支发布冻结、并发及远端 SHA。自动路径**不能声称独立人类批准已发生**。它不会自动合并 PR #144，也不会标记任务 DONE。

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

当前 GitHub 连接已实际创建 owner-authored `probe` Issue #286，GitHub `issues.opened` 自动工作流 #44980594304 成功，脱敏回执确认状态 SHA 未变。**唯一尚未验证的关键能力是专用 App 的真实 Contents:write 与受保护状态分支非强制 Git CAS 推送**；不能因为 Issue 创建或 probe 成功就声称写入链路可用。后续写入必须由用户单独明确授权，并复核工作流、回执和实际远端 SHA。

非所有者请求、改写过的 Issue、非 `main` 来源、错误版本/凭证、额外 JSON 字段、重复操作碰撞和错误 Git SHA 都应失败关闭。权限不匹配时没有状态提交。不支持未经审查的 `accept`、`close` 或任意 Schema 修改。公开回执不写入认证 Token 或任何私密信息。
