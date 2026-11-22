# 受保护状态 V0→V1 一次性迁移

> **当前状态（2026-11-22）**：协作源代码已通过 [PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) 合并到受保护 `main`（集成提交 `3177009eeb692c766715ba0c6e1133844f469981`）；合并后 CI 34/34 成功。[只读探针 Issue #286](https://github.com/micor-cjj-spec/matrix-prp/issues/286) / [Actions #44980594304](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44980594304) 成功，专用 App 的 Contents:read 单仓库验证完成，正式状态 SHA 未变。**V0→V1 尚未执行、PR #144 仍为 Draft、未获得独立审查、Contents:write 与真实保护分支推送尚未验收，生产发布冻结有效。**

来源：[已合并代码 PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271)、[受保护状态 V1 提案 PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)、[安全审查 Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147)、[零点击需求 Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。旧 Draft PR #138 仍在，但不可再次直接合并过期信任根代码。

**当前没有执行迁移。** 正式状态 `prp-collab-state` 仍是 V0：`062036f7021e215ffbfdcbf5689d207a0549b68b`，原有五个任务 READY，零领取。`prp-collab-automation` 的只读 Issue→Actions→App 探针已验收，但这不证明写入权限；真实迁移另需用户明确授权。

## 固定迁移对象

- 正式 V0 状态 SHA：062036f7021e215ffbfdcbf5689d207a0549b68b
- V1 提案 SHA：bf80d5c384d5f687cb980b6e04127fc42167d7a8
- 唯一状态文件：requirements/REQ-20261031-001.json
- 唯一迁移动作：从固定 V0 的五个任务迁移到 PR #144 提案的九个任务。
- **通用硬约束**：PR #144 必须先退出 Draft，保持固定提案 SHA；固定旧状态 SHA、单文件九任务精确变更、单仓库 App、主/状态分支 Ruleset 和发布冻结必须通过检查，任何当前提案 SHA 上的 `CHANGES_REQUESTED` 都不应被忽略。**独立审查要求须按调用入口区分**，参见下节；不能把单人所有者授权写成“独立审查已通过”。

迁移必须保持原五个任务的 READY/null-claim 状态和空请求账本；仅允许将原 T-003 依赖精确调整为 T-001/T-007/T-009、修正 T-005 验收依赖，并精确新增 T-006～T-009 四个任务。严禁借此更改历史任务其他字段或扩大文件白名单。任何额外字段、路径、依赖、历史状态变化或 SHA 漂移均拒绝。

## 迁移授权路径与安全保证

这里将“用户不用反复点击 GitHub 审批”与“是否经过独立人类代码审查”严格区分，按当前受保护 `main` 的实际实现描述：

- **ChatGPT / owner-authored Issue 自动入口**（`issues.opened` → `issue-migrate.mjs`）：运行时代码要求真实仓库所有者身份、固定请求字段与 UUID、PR #144 非 Draft、精确旧状态和提案 SHA、App 单仓库权限、Ruleset 与发布冻结；该路径由 `verifyOwnerIssuedApproval` 校验，**目前不会强制存在独立非所有者 `APPROVED` review**，但会拒绝当前提案 SHA 上的 `CHANGES_REQUESTED`。这是一人授权的机器校验路径，不代表已经独立审查。
- **旧手动 `workflow_dispatch` 入口**（`migration-transaction.sh`）：`mode=apply` 通过 `verifyIndependentProposalReview`，要求非仓库所有者、非作者，且 `author_association` 为 `COLLABORATOR` / `MEMBER` 的人类审查者对固定 SHA 最新有效的 `APPROVED` review；机器人、自审或旧 SHA 批准无效。
- **待完成的治理决议**：原审批文档曾将独立人类批准描述为所有入口强制要求，与上述已实现的所有者 Issue 例外不符。正式迁移前应在 [Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147) 明确选择“一次性独立人类审查 + 之后零重复点击”的较强控制，或明确接受 owner-only 例外的单人保证及其风险。**本说明不做该安全决策，不授权任何实际迁移。**

## ChatGPT 零点击迁移入口

正式执行前，仅在用户明确要求“执行 V0→V1 迁移”并且上面的治理模式已确定时，才能考虑将 PR #144 从 Draft 标记为 Ready for review，核对固定提案 SHA 并创建 owner-authored `[PRP-COLLAB-REQUEST]` Issue（`action=migrate_v1`）。如果选定独立审查模式，应先获得符合要求的当前 SHA 批准；如果经另行明确接受 owner-only 模式，不能声称独立人类审核已完成。请求携带固定 V0/提案 SHA；迁移脚本只使用固定的内部 apply acknowledgement，不接受任意用户字符串。普通“继续”不能触发迁移。

GitHub issues.opened 自动触发 main 上的 Issue ingress。该工作流：

1. 验证请求 Issue 的原始事件、仓库所有者身份、当前 Issue 和严格 JSON schema。
2. 校验固定 V0/提案 SHA、PR #144 非 Draft、仓库/base/head/单文件差异及精确五到九任务迁移；独立 reviewer 核验仅属于手动 apply 路径，当前自动 owner Issue 路径使用经过认证的 owner 例外并拒绝精确 SHA 的反对审查。
3. 校验 main 与状态分支保护、状态 Ruleset、专用 App ID/Ruleset ID、App installation token 的单仓库范围和生产发布冻结。
4. 在受保护的 prp-collab-automation Environment 中签发单仓库 App token。
5. 只写 requirements/REQ-20261031-001.json，执行一次非强制 Git push，并重新读取远端状态 SHA。
6. 只有远端 SHA 与新提交一致且成功回执已发布，才报告迁移成功。

owner-authored Issue 是自动入口对此次指定迁移的机器可验证授权事件，**无需用户再次手动点击 GitHub Actions / Required reviewers**；但它不证明第三方独立人类审查存在，且前述单人/独立审核治理选择仍未完成。普通“继续 PRP”、领取任务或创建任务请求不代表迁移授权。

## 一次性启用前置条件

- 协作源代码已由获授权的 PR #271 合并到受保护 `main`；旧 PR #138 仍为历史 Draft，不得再用它覆盖已修复的协调器或迁移校验逻辑。
- prp-collab-automation Environment 已配置：无 Required reviewers、无 Wait timer、唯一 custom deployment branch policy 为 main。
- Environment secret PRP_COLLAB_APP_PRIVATE_KEY 和三个变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID、PRP_COLLAB_RULESET_ID 已配置。
- 状态分支 Ruleset #26294671 和 main Ruleset #24968649 保持有效；main 发布冻结保持有效。
- 先完成一次 Contents:read 只读 probe，确认状态 SHA 不变；再经单独明确授权，完成一次 Contents:write 低影响试点。

旧 prp-collab-migration workflow 保留为 legacy 手动路径；它不是 ChatGPT 日常入口。新 Issue ingress 的 migrate_v1 才是无逐次 GUI 审批的路径。

## 迁移边界

迁移不会合并 PR #144，不会合并 bootstrap PR #138，不会接受或完成任务，不会领取任务，不会修改生产数据，不会部署，也不会解除 publication hold。V1 生效后，新任务登记仍需通过 register_task 请求；新登记任务先进入 READY，领取是独立操作。

当前 PR/CI 状态不构成迁移授权。不得 force-push、绕过 Ruleset 或手工改写状态 JSON。
