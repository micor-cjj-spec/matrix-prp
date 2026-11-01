# Bootstrap PR reconciliation — REQ-20261031-001

PR #138 是初始 bootstrap 候选实现，目标分支为 main；它不是五个独立任务 PR 的集合。prp-collab-state 仍为 V0，当前 SHA 为 062036f7021e215ffbfdcbf5689d207a0549b68b，五个历史任务均 READY、无 claim。

## 当前文件范围审计（2026-11-01）

根据 Draft PR #138 的完整 GitHub changed-file 列表，并使用 Draft PR #144 的九任务 scope proposal 逐文件匹配：

- PR changed files：66
- 唯一映射到普通任务 scope：49
- bootstrap/governance-only：17
- 同一 changed file 同时落入多个任务 scope：0

普通任务 scope 的文件数：
- T-001：2
- T-002：3
- T-003：3
- T-004：11
- T-005：0
- T-006：9
- T-007：12
- T-008：5
- T-009：4

17 个 bootstrap-only 文件必须作为信任根单独审查，不得通过普通任务 PR 修改：

- .github/workflows/ci.yml
- .github/workflows/feature-impact.yml
- .github/workflows/prp-collab-issue-ingress.yml
- .github/workflows/prp-collab-migration.yml
- .github/workflows/prp-dev-collab-contract.yml
- app/scripts/dev-collab/issue-ingress.mjs
- app/scripts/dev-collab/issue-ingress.test.mjs
- app/scripts/dev-collab/issue-migrate.mjs
- app/scripts/dev-collab/issue-migrate.test.mjs
- app/scripts/dev-collab/issue-transaction-git.test.mjs
- app/scripts/dev-collab/issue-transaction.mjs
- app/scripts/dev-collab/issue-transaction.test.mjs
- app/scripts/dev-collab/migration-guard.mjs
- app/scripts/dev-collab/migration-guard.test.mjs
- app/scripts/dev-collab/migration-transaction.sh
- app/scripts/dev-collab/migration-transaction.test.mjs
- app/scripts/dev-collab/task-scope-policy.mjs

只读审计脚本不会修改 refs、Issues、PR、状态文件或服务器。每次审查都应从实时 GitHub changed-file 列表和精确 V1 proposal 重新生成结果，不应依赖历史计数。

## 当前安全配置证据

- prp-collab-state Ruleset #26294671 已启用，唯一配置的 bypass actor 为专用 Integration App 5561446。
- main Ruleset #24968649 已启用，bypass actors 为空。
- main 的 app/deploy/publication-hold.json 仍有效。
- 状态分支仍为 V0；PR #144 是 Draft 提案，尚未应用。
- PR #138 仍为 Draft，尚未合并。

## 零点击入口候选实现

PR #138 已包含 owner-authenticated Issue ingress，支持 claim、进度、checkpoint、handoff、takeover、register_task 和固定 migrate_v1。正常操作由 ChatGPT 创建 [PRP-COLLAB-REQUEST] Issue，GitHub issues.opened 自动触发；不需要逐次 workflow_dispatch 或 Required reviewers 点击。

新任务登记通过两个 owner-authored Issue 完成：先创建 Task Issue 和 PRP_TASK_MANIFEST，再创建 register_task 请求 Issue。工作流验证作者、manifest、依赖和 scope，成功后登记为 READY；领取仍是独立操作。

V0→V1 迁移通过固定 SHA 的 migrate_v1 请求执行。用户必须明确在 ChatGPT 中要求迁移；普通“继续 PRP”不代表迁移授权。该请求本身就是所有者授权，不需要额外 GUI approve。

## 尚未完成的真实启用条件

1. 对 17 个 bootstrap-only 文件完成信任边界审查，特别是 Issue 事件验证、App token 签发、Ruleset 校验、CAS 写入、迁移脚本和 task-scope-policy。
2. PR #138 仍为 Draft；尚未合并到 main，因此 Issue ingress 尚未在 main 上运行。
3. prp-collab-automation Environment 的 secret、variables、无审批规则和 main-only custom deployment branch policy 尚未完成真实核验。
4. 尚未完成真实 issues.opened → App installation token → prp-collab-state CAS → 远端 SHA → 脱敏回执端到端验收。
5. PR #144 尚未应用，正式状态保持 V0。

旧 prp-collab-controller Environment 和手动协调器保留为 legacy 路径。accept / close 不在 Issue ingress 的允许操作中，仍走独立可信验收流程。

## 不可越过的边界

本审计和文档更新不会自动合并 PR #138/#144，不会执行 V0→V1，不会将任务标记为 DONE，不会合并生产 PR，也不会解除 publication hold。只有在候选代码审查、一次性 Environment 配置和真实 Issue/App 写入验收完成后，才可考虑启用。
