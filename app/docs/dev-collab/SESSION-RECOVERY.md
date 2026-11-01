# GPT 会话接管与持久化恢复（零点击候选实现）

需求：[Issue #145](https://github.com/micor-cjj-spec/matrix-prp/issues/145)、[零点击操作要求 #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。代码位于 Draft PR #138，尚未合并到 main，真实 Issue 事件和 GitHub App 写入尚未验收。

## 权威状态与恢复边界

- prp-collab-state 分支中的 requirements/<REQ-ID>.json 是任务状态唯一权威来源；聊天记录不是任务状态数据库。
- 新会话先读取最新状态版本、任务状态、claim、checkpoint、PR、分支和 SHA，再决定继续、交接或接管。
- worker_id 只是会话标签，不是 ChatGPT 会话身份凭证。GitHub Issue 和状态分支均公开可读，claim_id 也不能当作秘密认证因素。
- 不要把私有聊天全文、密码、Token、PEM、个人数据或其他秘密写入 Issue、状态文件或 Actions 日志。
- 未提交、未推送的代码和私有聊天上下文不能保证恢复。只有 GitHub 远端已有的分支和提交可以核验。

## ChatGPT 零点击操作入口

候选入口为 .github/workflows/prp-collab-issue-ingress.yml：

1. 用户在 ChatGPT 明确提出任务操作。
2. ChatGPT 读取最新的 prp-collab-state 和目标任务信息，通过已连接的 GitHub 账号创建标题严格为 [PRP-COLLAB-REQUEST] 的 Issue，正文只包含该操作的严格 JSON。
3. GitHub 自动触发 main 上的 issues.opened 工作流。工作流校验仓库、事件来源、所有者身份、原始 Issue 与当前 Issue 一致性、操作字段白名单和状态版本。
4. 通过单仓库 GitHub App token 对 prp-collab-state 做单文件、非强制 Git CAS 更新，并核验远端 SHA。
5. 工作流把不含领取凭证的结果回执写回请求 Issue。ChatGPT 必须读取回执和最新状态 SHA，才能报告成功。

正常领取、进度、暂停/恢复、断点、交接、接管和任务登记不需要每次打开 Actions、点击 Run workflow 或点击 Required reviewers。该能力目前仍在 Draft PR #138 中，尚未启用。

## 操作语义

- claim：领取 READY 任务。每次操作使用新的 request_id；成功后由状态文件保存 claim_id、worker_id 和 generation。
- start / progress：开始任务或更新进度。进度更新不是每次对话都必须执行的审批步骤。
- checkpoint：按需要保存摘要、下一步、远端分支和精确 SHA。它是可选的持久化动作，不要求每个任务、每次进度更新都保存。
- handoff：原持有者主动交接给新会话。当前状态机要求存在可核验 checkpoint，并校验旧 claim、版本和远端 SHA。
- takeover：用户在 ChatGPT 中明确要求接管旧会话时，由 ChatGPT 创建 owner-authored 请求 Issue；该请求本身就是这次接管的明确授权，不需要再去 GitHub 点审批。必须校验旧 claim、expected_version、分支和 SHA，并轮换 claim_id 与 generation，使旧 claim 立即失效。
- 无 checkpoint 的 takeover：允许用户基于已存在的 GitHub 证据重建最小 checkpoint，但必须提供现存的非 main 分支及准确 SHA；工作流用 git ls-remote 验证远端分支头。没有远端分支或 SHA 不匹配时拒绝写入。
- submit：提交任务 PR 编号和准确 head SHA，进入 IN_REVIEW；这不等于 PR 已获批准或已合并。
- release / pause / block / resume / rework：按状态机执行，不需要重复 GitHub GUI 审批。

禁止仅因旧会话长时间没有活动就自动抢占。接管必须来自用户在 ChatGPT 中的明确指令。

## 一次性 V0→V1 迁移

REQ-20261031-001 当前仍是 V0。用户明确要求迁移时，ChatGPT 才创建 owner-authored [PRP-COLLAB-REQUEST] Issue，执行 action=migrate_v1。

该动作只允许固定的 V0 SHA 062036f7021e215ffbfdcbf5689d207a0549b68b 和固定提案 SHA fb57656dca6df5f12e083fc0430263b4d88e452d。工作流还必须验证 PR #144、九任务精确差异、状态分支 Ruleset、单仓库 App 范围、main 发布冻结和远端 SHA。此次 Issue 是一次性迁移的明确授权，不再要求额外 GitHub GUI approve；不支持任意版本升级或任意 schema 修改。

“继续 PRP”或普通任务操作不自动代表同意执行 V0→V1 迁移。

## 新会话接续步骤

1. 读取 prp-collab-state 的最新 commit SHA 和 requirements/REQ-20261031-001.json。
2. 找出目标任务当前状态、依赖、claim、checkpoint、PR、分支和 head SHA。
3. 对已有分支执行远端 SHA 核验；对 PR 读取当前 head、review 和 CI，不从旧聊天摘要推断代码状态。
4. 若当前任务属于另一个会话，按用户指令执行 handoff 或 takeover；不要猜测旧会话是否失效。
5. 只有状态写入成功且读取到远端 SHA 回执后，才更新任务状态结论。

## 当前验收边界

- PR #138：Draft，尚未合并。
- PR #144：Draft V0→V1 提案，尚未应用。
- Issue #147：bootstrap 信任边界独立审查仍未关闭。
- Issue #148：零点击入口要求仍未完成真实 GitHub 端到端验收。
- prp-collab-state：仍为 V0；不因代码 CI 通过而提前迁移。
- main 的生产发布冻结保持有效；不执行生产发布。

本文件描述候选实现，不表示生产级接管或自动写入已经启用。
