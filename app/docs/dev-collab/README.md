# Matrix PRP 跨会话任务协作 — MVP 候选实现

父需求：[Issue #132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)。
跨会话恢复：[Issue #145](https://github.com/micor-cjj-spec/matrix-prp/issues/145)。
零点击操作：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。
核心候选实现：[Draft PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)。
V0→V1 状态提案：[Draft PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)。

## 权威状态与安全边界

- 每个 requirement 有一个状态 JSON：requirements/<REQ-ID>.json。
- 受保护的 prp-collab-state Git 分支是任务状态唯一权威来源；Issue、评论、标签和 ChatGPT 对话都不是互斥锁或权威状态库。
- main 保持受保护。协作工作流不自动合并 PR、不部署生产、不运行 SSH、不访问生产数据库/Keycloak，也不安装 MCP。
- 公开仓库和状态分支不得保存私密聊天全文、密码、Token、PEM、个人敏感信息。worker_id 是会话标签，不是 ChatGPT 会话 ID 或认证凭证。
- 当前实现仍在 Draft PR #138，尚未合并到 main。prp-collab-automation Environment 和真实 Issue 事件/App 写入尚未完成验收；不能因为 CI 通过就宣称已上线。

## ChatGPT 日常操作入口

正式启用后，日常任务操作直接在 ChatGPT 中提出。ChatGPT 读取最新状态，然后以仓库所有者身份创建标题严格为 [PRP-COLLAB-REQUEST] 的 Issue。GitHub issues.opened 自动触发 main 上的 Issue ingress 工作流，校验原始事件、作者、请求 schema、状态版本和 App 范围，再通过单文件非强制 Git CAS 写入状态分支，并将脱敏回执写回请求 Issue。

支持的操作包括：

- claim、start、progress；
- pause、block、resume、release；
- 按需 checkpoint；
- handoff、明确授权的 takeover；
- submit、rework；
- V1 生效后的 register_task；
- 用户明确要求时执行固定 V0→V1 的 migrate_v1；PR #144 必须完成独立审查并退出 Draft，ChatGPT 可在明确迁移授权后将其标记为 Ready for review，但不会合并该 PR。

日常任务操作不需要逐次打开 Actions → Run workflow，也不需要逐次点击 Required reviewers。一个操作请求 Issue 就是该次操作的明确所有者授权；创建 Issue 本身不等于状态写入成功，必须读取工作流回执和最新远端 SHA。

## 任务生命周期与跨会话恢复

常规流程为 READY → CLAIMED → IN_PROGRESS → IN_REVIEW → DONE。支持 BLOCKED、PAUSED、恢复和 release。

- progress 不要求每次对话都更新。
- checkpoint 是可选的持久化动作，不要求每个任务或每次进度更新都保存。
- 主动 handoff 要求可核验 checkpoint。
- takeover 必须由用户明确要求。若没有 checkpoint，可根据已存在的远端分支和准确 SHA 重建最小恢复点；没有远端证据时不能恢复未提交代码。
- 不得仅因旧会话长时间无活动就自动抢占。
- worker_id 只是任务记录标签，不能证明某个 ChatGPT 会话仍然存活，也不能恢复私有聊天上下文。

## 新任务登记

V1 状态生效后，ChatGPT 创建新任务时会自动完成两步：

1. 创建 owner-authored Task Issue，包含唯一 PRP_TASK_MANIFEST JSON。
2. 创建 [PRP-COLLAB-REQUEST] Issue，执行 register_task，引用任务 Issue 和最新状态版本。

工作流会重新读取并校验 Task Issue 的作者、标题、状态、manifest、依赖和文件范围，再把任务登记为 READY。登记不会自动领取；用户要求立即开始时，再单独执行 claim。任务 scope 不允许修改协作治理、GitHub Actions 工作流、迁移或信任根文件。

## 一次性启用条件

1. 完成 PR #138 的 bootstrap 信任边界审查，并由仓库所有者授权合并。
2. 一次性配置 prp-collab-automation Environment：不配置 Required reviewers 或 Wait timer；custom deployment branch policy 只允许 main。
3. 配置 Environment secret PRP_COLLAB_APP_PRIVATE_KEY，以及变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID=5561446、PRP_COLLAB_RULESET_ID=26294671。
4. 专用 GitHub App 只安装到 micor-cjj-spec/matrix-prp；每次 token 限定该仓库。
5. 先用 Contents:read 执行一次真实只读 probe，确认 Actions、App token 单仓库范围、脱敏回执和状态 SHA 完全未变；随后经单独明确授权，再执行一次低影响 Contents:write 试点，核验非强制 CAS 推送和新远端 SHA。

旧 prp-collab-controller Environment 和手动协调器作为独立旧路径保留，不是日常任务操作入口。accept / close 不在 Issue ingress 的允许操作中，仍走独立可信验收流程。

## 当前真实状态（2026-11-01）

- prp-collab-state 仍为 V0，SHA：062036f7021e215ffbfdcbf5689d207a0549b68b；五个任务均 READY。
- 状态分支 Ruleset #26294671 已启用，唯一 bypass 是专用 Integration App 5561446。
- main Ruleset #24968649 已启用，没有 bypass actors。
- main 的 app/deploy/publication-hold.json 仍有效，生产发布冻结保持。
- PR #138 和 PR #144 均为 Draft；没有执行 V0→V1 迁移，也没有生产发布。
- CI 和专项测试只证明候选代码，不证明真实 Environment 或 App 写入已经启用。

请求账本每个 requirement 最多保留 512 条记录，满额后 fail closed；归档/重新分钥匙需要单独审查。
