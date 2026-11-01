# PRP Collaboration MVP：操作方式与安全边界

父需求：[Issue #132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)。
核心实现：[Draft PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)。
状态迁移提案：[Draft PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)。
独立信任边界审查：[Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147)。
零点击操作要求：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。

## 当前状态

当前实现仍在 Draft PR #138，尚未合并到 main；GitHub Issue 自动入口尚未真实触发，专用 App token 的状态分支写入尚未验收。代码测试通过不等于生产启用。

GitHub 的 prp-collab-state 分支保存 requirements/<REQ-ID>.json，是任务状态唯一权威来源；它不是 PRP 生产数据库。仓库为公开仓库，禁止在状态文件、Issue 或日志中保存私密聊天全文、Token、私钥、密码或个人敏感信息。

## 正式启用后的日常操作：直接在 ChatGPT 中完成

日常入口为 .github/workflows/prp-collab-issue-ingress.yml，触发方式是 GitHub issues.opened，而不是 workflow_dispatch。

用户在 ChatGPT 中提出领取、开始、更新进度、暂停/恢复、阻塞、释放、保存断点、主动交接、接管旧会话、提交 PR 或登记新任务等明确要求后，ChatGPT 读取最新状态，并通过已连接的 GitHub 所有者身份创建 [PRP-COLLAB-REQUEST] Issue。GitHub 自动运行 main 上的受信任工作流，验证原始事件、Issue 作者、当前 Issue、严格 JSON schema、状态版本和 GitHub App 写入范围，再通过单文件非强制 Git CAS 更新状态分支。

成功必须同时满足：工作流完成、回执明确、远端状态 SHA 与预期提交一致。创建 Issue 本身不代表任务状态已改变。失败或状态版本过期时，ChatGPT 重新读取状态后再发起新请求。

该流程不要求日常操作逐次点击 Actions → Run workflow，也不要求逐次点击 Required reviewers。worker_id 是会话标签，不是 ChatGPT 会话身份凭证；公开的 claim_id 不是秘密。

## 一次性启用前置条件

1. 对 PR #138 中的所有 bootstrap / workflow / GitHub App 信任边界变更完成独立审查，并由仓库所有者单独授权合并。Issue #147 尚未关闭。
2. 在 GitHub 一次性配置专用 Environment：prp-collab-automation。Deployment branches 限制为 main；该自动化 Environment 不配置 Required reviewers 或 Wait timer。
3. 在该 Environment 配置 secret PRP_COLLAB_APP_PRIVATE_KEY，以及变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID=5561446、PRP_COLLAB_RULESET_ID=26294671。不要把私钥或 Token 交给 ChatGPT，也不要写入 Issue。
4. 专用 GitHub App 只安装到 micor-cjj-spec/matrix-prp，并只申请所需的最小仓库权限。自动入口只请求单仓库 Contents: write。
5. 保留 prp-collab-state 的精确 Ruleset #26294671：仅匹配 refs/heads/prp-collab-state，要求 update、deletion、non_fast_forward 限制，唯一 bypass 为专用 Integration App。
6. 保留 main 的保护 Ruleset #24968649，不给协作 App main bypass；保留 app/deploy/publication-hold.json 的生产发布冻结。
7. 完成一次低影响真实 Issue opened 事件验收，核对 Actions 运行、App installation token、状态分支提交 SHA 和脱敏回执。

不要为了绕过审批而解除现有保护。旧的 prp-collab-controller Environment 保持不变；它不作为日常 Issue 自动入口的审批路径。

## 一次性 V0→V1 迁移

REQ-20261031-001 当前正式状态仍为 V0，包含五个 READY 任务。PR #144 提出九任务 V1 状态文件，但尚未应用。

用户在 ChatGPT 中明确要求执行迁移后，自动入口接受唯一固定的 migrate_v1 请求。该 owner-authored Issue 代表这次迁移的明确授权，不再要求额外 GitHub GUI approve。工作流仍须验证固定 V0 SHA、固定提案 SHA、PR #144 的身份和单文件九任务精确差异、专用 App 单仓库范围、Ruleset、main 发布冻结、并发状态和远端提交结果。

该功能不支持任意版本迁移。普通“继续 PRP”、领取任务或创建任务的请求，不代表同意迁移。迁移完成前不允许登记 V1 新任务。

## 新任务创建与登记

V1 生效后，创建新任务分两步，均可由 ChatGPT GitHub 连接自动完成，不需要用户打开 GitHub：

1. 创建 owner-authored Task Issue，标题为 [TASK][REQ-ID/T-NNN] 标题；正文包含目标、验收标准和唯一的 PRP_TASK_MANIFEST JSON 清单。
2. 创建 [PRP-COLLAB-REQUEST] Issue，action=register_task，引用 Task Issue 编号、标题、依赖、允许路径和最新状态版本。

工作流会重新读取 Task Issue，校验作者、标题、Issue 状态和机器清单，然后通过 CAS 将任务登记为 READY。登记成功不等于自动领取；如用户要求立即开始，ChatGPT 再发起 claim 操作。任务编号必须连续，依赖必须存在，文件范围必须符合 task-scope-policy.mjs 的白名单。协作治理工作流、迁移、部署配置和信任根文件不属于普通任务范围。

## 任务状态和代码审查边界

- claim / start / progress / pause / block / resume / release：由所有者 Issue 触发的自动状态事务。
- checkpoint：按需要记录可恢复的摘要和 Git 远端分支/SHA，不要求每次对话都写断点。
- handoff / takeover：必须明确指定目标会话标签并校验旧 claim、状态版本和远端 SHA；不能仅凭会话沉默自动接管。
- submit：记录 PR 编号和准确 head SHA，不代表 PR 已获批准。
- accept / close：当前不在零点击 Issue ingress 的允许操作中，仍需独立可信的 PR、CI、集成分支和验收证据；不能通过普通任务请求将任务直接标为 DONE。
- 不自动合并任务 PR，不自动合并 bootstrap PR，不自动执行生产部署。

## 只读任务看板

app/scripts/dev-collab/board.mjs 从状态文件生成只读任务看板，展示需求、任务、状态、依赖、worker 和 PR。看板不包含 claim 凭证，也不授权领取、验收、合并或部署。

## 当前验证证据（2026-11-01）

Draft PR #138 当前 head：26310b21d210b340b48819981dff87df2f164d14。

当前该精确 HEAD 的 CI、Feature Impact Report、PRP Dev Collaboration Contract 三个工作流均已成功；CI 工作流的九个 Job 全部成功，合计 11/11 检查通过。这证明当前候选代码通过了 GitHub Actions 验证，不代表 Issue 自动触发、Environment 配置或 GitHub App 实际状态写入已经完成。

实时核验的仓库安全配置：
- 状态分支 Ruleset #26294671 已启用，仅允许专用 Integration App bypass。
- main Ruleset #24968649 已启用，没有 bypass actors。
- main 的 app/deploy/publication-hold.json 仍存在，生产发布冻结保持有效。
- prp-collab-state 当前 SHA 仍为 V0：062036f7021e215ffbfdcbf5689d207a0549b68b。

## 验证命令

```bash
node --test app/scripts/dev-collab/*.test.mjs
bash -n app/scripts/dev-collab/state-transaction.sh
```

不要在本地测试通过后声称 GitHub 自动入口已经上线。真实验收必须以 GitHub Actions 运行、专用 App 实际写入和远端状态 SHA 为准。
