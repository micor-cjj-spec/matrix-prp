# REQ-20261031-001 — 单人 Owner / ChatGPT 对话批准（候选）

> **Draft-only / NO MERGE / NO LIVE STATE WRITE / NO PRODUCTION DEPLOY**。需求 #265。该文档描述候选门禁，不代表已经激活。

## 用户操作路径

由 PRP 唯一所有者在 ChatGPT 会话里明确同意 **特定动作及具体目标**，ChatGPT 使用已连接 GitHub 工具创建 Owner-authored 的 `[PRP-COLLAB-REQUEST]` Issue。GitHub 认证的 Issue 作者和可信 `issues.opened` event 由 **main 上经过审查的** GitHub Actions 逐项核对；不是把聊天文字当作平台身份。

- “我选择单人治理”只批准设计和代码准备，不批准合并、迁移、上线。
- “批准迁移 REQ-20261031-001 V0→V1，按 #144 精确版本执行”经 ChatGPT 理解后，使用准确的 request UUID 和固定 state/proposal SHA 发起一次专用 Issue。没有这句针对具体目标的批准，就不能发起迁移。
- GitHub Issue 必须由 Owner 账号 `micor-cjj-spec` (ID `123868412`) 创建，不能由非 Owner 机器人身份代替。核查 `event.sender`、Issue user、事件/当前 Issue 内容一致与未关闭。
- 受保护 main 发布冻结、受保护状态分支、唯一 GitHub App 绕过、单仓安装权限、PR #144 exact-head、修改路径、任务 DAG、review objections 和 Git CAS 都要通过。
- 迁移 PR #144 必须取消 Draft，但**取消 Draft 不是授权**；只有另外明确的 Owner 请求才授权执行。
- 真正写入前再次读取当前 GitHub Issue、PR/文件/评审/Ruleset/App 和三个远端分支 SHA；失败即停止。成功后脱敏 Issue receipt 记录新 SHA。
- 两个 GPT 会话使用同一个 GitHub Owner 身份；`worker_id` 仅为防止意外冲突的协作标签，不提供独立会话强身份隔离。

## 与原有审查路径的边界

`verifyMigrationEvidence` 默认仍要求独立 `APPROVED`。只有**可信 `issue-migrate.mjs` 调用**传入从 `validateIssueEvent` 获得并在提交前重新验证的 `ownerIssue`，才切换单人策略；该策略仍要求 `mode=apply`、准确 V0/V1 SHA、未处于 Draft、单仓 App 范围、不存在精确版本的 `CHANGES_REQUESTED` 评审。普通 CLI 和 `workflow_dispatch` 不暴露 `ownerIssue` 参数，仍保持原门禁。

Owner Issue 的形状字段不构成独立的密码学证明；它必须始终与 GitHub 原始事件、当前 Issue、仓库身份和受保护主分支的可信执行上下文结合。不可将此 helper 暴露为任意用户可调用的权限接口。

## 只读上线前核验

1. 先核对候选 PR 的精确 SHA 与所有 CI 结论（包括失败/取消/未覆盖的作业），保留可复现测试；安全代码和紧邻 push 的 TOCTOU 窗口在单人治理下是自审风险。
2. 由 Owner 通过 ChatGPT **分别明确批准** 主分支受控集成、只读 App 环境探针、V1 迁移和试点写入；不要把本 Issue #265 视作这些批准。
3. 在真实 GitHub 上核验 App/Environment 变量权限和 owner-authored Issue 触发，先执行只读 probe，不使用生产 SSH、DB、Keycloak、MCP 个人数据。
4. V1 真正迁移后核对版本、任务数、SHA 与收据，再用两个真实会话验证并发 claim、stale version、progress、handoff、takeover 和任务审批。
5. 发布冻结 `app/deploy/publication-hold.json` 不得被单人协作流程解除。生产部署永远需要单独批准。

## 风险与回滚

本方案在私人项目中省略第二人审查，是**单人治理**而非“已通过独立安全审查”；主风险是 Owner 的 GitHub 连接或 ChatGPT 发起的动作被错误授权。允许撤销/关闭未执行 Issue（执行前必须重读状态），拒绝任意事后修改操作；状态写入只通过非强制 Git CAS，并保留日志。迁移如果已经完成，不能单纯重放或强制回退受保护状态，应通过独立审批的补偿迁移并检查下游任务操作。

真实 App 凭证、Environment 设置、GitHub Actions 激活和双会话验收目前**未得到确认**。
