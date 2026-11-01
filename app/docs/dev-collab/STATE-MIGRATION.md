# 受保护状态 V0→V1 一次性迁移

来源：[Draft PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)、[Draft PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)、跟踪 [Issue #139](https://github.com/micor-cjj-spec/matrix-prp/issues/139)。

**当前没有执行迁移。** 正式状态仍为 V0。PR #138 尚未合并到 main，prp-collab-automation Environment 和真实 Issue/App 写入尚未验收。

## 固定迁移对象

- 正式 V0 状态 SHA：062036f7021e215ffbfdcbf5689d207a0549b68b
- V1 提案 SHA：fb57656dca6df5f12e083fc0430263b4d88e452d
- 唯一状态文件：requirements/REQ-20261031-001.json
- 唯一迁移动作：从固定 V0 的五个任务迁移到 PR #144 提案的九个任务。
- PR #144 必须先退出 Draft，再在固定提案 SHA 上取得至少一名**非仓库所有者、非 PR 作者且 GitHub `author_association` 为 `COLLABORATOR`/`MEMBER` 的真实 GitHub 用户**的 `APPROVED` review；最新 review 必须仍为 `APPROVED`。若用户已明确授权迁移，ChatGPT 可以先将 PR 标记为 Ready for review；这一步只开放审查，不会写状态。独立 reviewer 批准后，ChatGPT 才创建最终 owner-authored migration Issue。对当前 SHA 的 `CHANGES_REQUESTED`、仅所有者自审、机器人 review、旧 SHA review 或不完整的 review 列表均 fail closed。若仍为 Draft 或缺少独立批准，mode=apply 必须拒绝。将 PR 标记为 Ready for review 不是合并，也不需要用户手动点击；真正的状态迁移仍只由随后经过校验的 owner-authored Issue 触发。

迁移必须保持原五个任务的 READY/null-claim 状态和空请求账本；仅允许精确增加四个新任务及已审查的 scope/dependency 差异。任何额外字段、路径、依赖、历史状态变化或 SHA 漂移均拒绝。

## ChatGPT 零点击迁移入口

正式启用后，只有用户在 ChatGPT 中明确要求“执行 V0→V1 迁移”，ChatGPT 才能先将 PR #144 标记为 Ready for review；待独立协作者对固定提案 SHA 完成审查并批准后，ChatGPT 才能创建 owner-authored [PRP-COLLAB-REQUEST] Issue，正文使用 action=migrate_v1。请求携带固定 V0/提案 SHA；迁移脚本内部注入一次性固定 apply acknowledgement，不接受任意 acknowledgement。

GitHub issues.opened 自动触发 main 上的 Issue ingress。该工作流：

1. 验证请求 Issue 的原始事件、仓库所有者身份、当前 Issue 和严格 JSON schema。
2. 校验固定 V0 SHA、固定 V1 提案 SHA、PR #144 已非 Draft、至少一名独立人类 reviewer 对精确提案 SHA 的最新 `APPROVED` review、仓库/base/head/单文件差异和精确五到九任务迁移。
3. 校验 main 与状态分支保护、状态 Ruleset、专用 App ID/Ruleset ID、App installation token 的单仓库范围和生产发布冻结。
4. 在受保护的 prp-collab-automation Environment 中签发单仓库 App token。
5. 只写 requirements/REQ-20261031-001.json，执行一次非强制 Git push，并重新读取远端状态 SHA。
6. 只有远端 SHA 与新提交一致且成功回执已发布，才报告迁移成功。

owner-authored Issue 本身就是这次迁移的明确授权，不再要求额外点击 GitHub Required reviewers 或手动 Run workflow。普通“继续 PRP”、领取任务或创建任务请求不代表迁移授权。

## 一次性启用前置条件

- PR #138 的 bootstrap 信任边界审查完成并经所有者授权合并到 main。
- prp-collab-automation Environment 已配置：无 Required reviewers、无 Wait timer、唯一 custom deployment branch policy 为 main。
- Environment secret PRP_COLLAB_APP_PRIVATE_KEY 和三个变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID、PRP_COLLAB_RULESET_ID 已配置。
- 状态分支 Ruleset #26294671 和 main Ruleset #24968649 保持有效；main 发布冻结保持有效。
- 先完成一次 Contents:read 只读 probe，确认状态 SHA 不变；再经单独明确授权，完成一次 Contents:write 低影响试点。

旧 prp-collab-migration workflow 保留为 legacy 手动路径；它不是 ChatGPT 日常入口。新 Issue ingress 的 migrate_v1 才是无逐次 GUI 审批的路径。

## 迁移边界

迁移不会合并 PR #144，不会合并 bootstrap PR #138，不会接受或完成任务，不会领取任务，不会修改生产数据，不会部署，也不会解除 publication hold。V1 生效后，新任务登记仍需通过 register_task 请求；新登记任务先进入 READY，领取是独立操作。

当前 PR/CI 状态不构成迁移授权。不得 force-push、绕过 Ruleset 或手工改写状态 JSON。
