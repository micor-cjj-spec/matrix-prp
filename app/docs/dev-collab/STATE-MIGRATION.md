# 受保护状态 V0→V1 一次性迁移

> **历史迁移已完成（2026-11-22）**：协作入口通过 [PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) 进入受保护 `main`，只读探针 [Issue #286](https://github.com/micor-cjj-spec/matrix-prp/issues/286) / [Actions #44980594304](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44980594304) 先验证了 Contents:read。随后所有者明确授权的 [Issue #324](https://github.com/micor-cjj-spec/matrix-prp/issues/324) / [Actions #44995074733](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44995074733) 成功执行 V0→V1、专用 App 受保护分支非强制 CAS 写入（初始 V1 SHA `683dbccf4620152c8ff127cdc557cfc82dde94a5`）。后续真实双会话、授权接管和释放已验收（[#139](https://github.com/micor-cjj-spec/matrix-prp/issues/139)、[#145](https://github.com/micor-cjj-spec/matrix-prp/issues/145)）。最近核验的正式状态为 SHA `6226ed6a706e20fe57e19a78c4b8119550996c1a`、V1 version **10**、9 READY、0 claim、9 条成功操作审计记录。一次性迁移**不可重复执行**；PR #144 已非 Draft 但没有合并，生产发布仍冻结。

来源：[受控源代码 PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271)、[迁移提案 PR #144（未合并）](https://github.com/micor-cjj-spec/matrix-prp/pull/144)、[正式迁移 Issue #324](https://github.com/micor-cjj-spec/matrix-prp/issues/324)、[安全治理 #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147)、[协作验收 #139](https://github.com/micor-cjj-spec/matrix-prp/issues/139)。旧 Draft PR #138 是历史候选，不能覆盖现有信任根。

**一次性迁移已经执行，以下是固定迁移对象与授权模型的历史审计记录。** 迁移前 V0 SHA 为 `062036f7021e215ffbfdcbf5689d207a0549b68b`，迁移后初始 V1 SHA 为 `683dbccf4620152c8ff127cdc557cfc82dde94a5`。后续成功任务操作已推进到版本 10。不得再向 ACTIVE V1 快照发起 `migrate_v1`，也不得把迁移提案 PR #144 合并视为状态变更的必要步骤。

## 固定迁移对象

- 正式 V0 状态 SHA：062036f7021e215ffbfdcbf5689d207a0549b68b
- V1 提案 SHA：bf80d5c384d5f687cb980b6e04127fc42167d7a8
- 唯一状态文件：requirements/REQ-20261031-001.json
- 唯一迁移动作：从固定 V0 的五个任务迁移到 PR #144 提案的九个任务。
- **历史执行约束**：迁移时要求 PR #144 非 Draft、精确旧状态/提案 SHA、单文件九任务差异、专用 App 单仓库身份、主/状态分支 Ruleset 和发布冻结均通过检查；拒绝固定提案 SHA 上的 `CHANGES_REQUESTED`。所有者采用方案 B 的机器校验授权路径，不得据此声称通过独立非所有者审查。以下约束保留供审计，不代表允许再次执行迁移。

迁移必须保持原五个任务的 READY/null-claim 状态和空请求账本；仅允许将原 T-003 依赖精确调整为 T-001/T-007/T-009、修正 T-005 验收依赖，并精确新增 T-006～T-009 四个任务。严禁借此更改历史任务其他字段或扩大文件白名单。任何额外字段、路径、依赖、历史状态变化或 SHA 漂移均拒绝。

## 迁移授权路径与安全保证

这里记录**已经完成的 V0→V1 迁移**时，两条入口分别采用的授权机制：自动 owner-authored Issue 路径和旧手动 `workflow_dispatch` 路径。无需反复操作 GitHub 与是否经过独立人类审查是两回事。

- **ChatGPT / owner-authored Issue 自动入口**（`issues.opened` → `issue-migrate.mjs`）：运行时代码要求真实仓库所有者身份、固定请求字段与 UUID、PR #144 非 Draft、精确旧状态和提案 SHA、App 单仓库权限、Ruleset 与发布冻结；该路径由 `verifyOwnerIssuedApproval` 校验，**目前不会强制存在独立非所有者 `APPROVED` review**，但会拒绝当前提案 SHA 上的 `CHANGES_REQUESTED`。这是一人授权的机器校验路径，不代表已经独立审查。
- **旧手动 `workflow_dispatch` 入口**（`migration-transaction.sh`）：`mode=apply` 通过 `verifyIndependentProposalReview`，要求非仓库所有者、非作者，且 `author_association` 为 `COLLABORATOR` / `MEMBER` 的人类审查者对固定 SHA 最新有效的 `APPROVED` review；机器人、自审或旧 SHA 批准无效。
- **实际使用的治理选择（2026-11-22，方案 B）**：所有者明确选择自动 owner-authored Issue 的 **owner-only 授权保证**，并在之后另行批准实际执行。该路径不要求独立人类 `APPROVED`，也**没有**发生独立非所有者审查；所有者单人授权与 PR 代码审查不能混淆。旧手动入口仍保持其更严格的独立 reviewer 条件。选择 B 不自动授予任何未来状态写入的授权。

## ChatGPT 零点击迁移入口

**迁移已完成，以下是历史执行方式，不是待执行事项。** 所有者先选择方案 B，后另行明确授权固定 V0→V1 迁移；#324 按固定 SHA 创建 owner-authored `[PRP-COLLAB-REQUEST]` Issue，Actions #44995074733 返回 Success 并完成远端 CAS 核验。PR #144 当时已非 Draft，未经过独立人类批准，也未合并。不得使用普通“继续”或重复创建历史 `migrate_v1` 请求。

GitHub issues.opened 自动触发 main 上的 Issue ingress。该工作流：

1. 验证请求 Issue 的原始事件、仓库所有者身份、当前 Issue 和严格 JSON schema。
2. 校验固定 V0/提案 SHA、PR #144 非 Draft、仓库/base/head/单文件差异及精确五到九任务迁移；独立 reviewer 核验仅属于手动 apply 路径，当前自动 owner Issue 路径使用经过认证的 owner 例外并拒绝精确 SHA 的反对审查。
3. 校验 main 与状态分支保护、状态 Ruleset、专用 App ID/Ruleset ID、App installation token 的单仓库范围和生产发布冻结。
4. 在受保护的 prp-collab-automation Environment 中签发单仓库 App token。
5. 只写 requirements/REQ-20261031-001.json，执行一次非强制 Git push，并重新读取远端状态 SHA。
6. 只有远端 SHA 与新提交一致且成功回执已发布，才报告迁移成功。

当时的 owner-authored Issue 是此**特定一次性迁移**的机器可验证授权事件，执行无需再点击 Actions / Required reviewers；它不代表第三方独立批准。固定 SHA/非 Draft/App/Ruleset/发布冻结检查在历史迁移中通过，后续新操作仍需明确授权和实时版本检查。普通“继续 PRP”、领取或注册任务绝不允许重放迁移。

## 一次性启用前置条件

- 协作源代码已由获授权的 PR #271 合并到受保护 `main`；旧 PR #138 仍为历史 Draft，不得再用它覆盖已修复的协调器或迁移校验逻辑。
- prp-collab-automation Environment 已配置：无 Required reviewers、无 Wait timer、唯一 custom deployment branch policy 为 main。
- Environment secret PRP_COLLAB_APP_PRIVATE_KEY 和三个变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID、PRP_COLLAB_RULESET_ID 已配置。
- 状态分支 Ruleset #26294671 和 main Ruleset #24968649 保持有效；main 发布冻结保持有效。
- **历史验收已完成：**先通过 #286 验证 Contents:read，再由单独授权 #324 验证 Contents:write 与受保护分支 CAS，均有 Actions 回执和真实远端 SHA。后续任务操作另行授权。以后不应重复执行一次性迁移。

旧 prp-collab-migration workflow 保留为 legacy 手动路径；它不是 ChatGPT 日常入口。新 Issue ingress 的 migrate_v1 才是无逐次 GUI 审批的路径。

## 迁移边界

迁移不会合并 PR #144，不会合并 bootstrap PR #138，不会接受或完成任务，不会领取任务，不会修改生产数据，不会部署，也不会解除 publication hold。V1 生效后，新任务登记仍需通过 register_task 请求；新登记任务先进入 READY，领取是独立操作。

**一次性迁移已执行，不得重复申请或重放。** 仅 CI 通过仍不构成未来敏感写入的授权；严禁 force-push、绕过 Ruleset、手动改写受保护状态 JSON 或解除发布冻结。
