# 零点击 Issue 自动化启用前检查（只读）

本检查只验证启用前置条件，不创建任务、不写状态分支、不合并 PR、不验收任务，也不部署生产。

## 当前已核实的 GitHub 状态（2026-11-01）

- main 分支受保护，Ruleset #24968649 已启用，当前 bypass actors 为空。
- prp-collab-state 分支受保护，Ruleset #26294671 已启用，只配置专用 GitHub App Integration ID 5561446，bypass mode 为 always。
- 正式状态仍为 V0，当前 SHA 为 062036f7021e215ffbfdcbf5689d207a0549b68b，五个任务尚未领取。
- main 中 app/deploy/publication-hold.json 仍存在，生产发布冻结有效。
- prp-collab-automation Environment 的 secret、variables、无审批规则和 main-only 部署分支策略，尚未完成真实核验。
- Draft PR #138 尚未合并，因此 Issue 自动入口目前不会在 main 上运行。

## 一次性自动化 Environment 配置

日常任务操作使用 prp-collab-automation，不使用旧的 prp-collab-controller 手动审批环境。

一次性配置要求：

1. Environment 名称：prp-collab-automation。
2. 不配置 Required reviewers，不配置 Wait timer。日常领取、进度、断点、交接、接管和迁移由 owner-authored Issue 作为明确授权事件，不再逐次点击 GitHub 审批。
3. Deployment branches and tags 使用 custom branch policies，且唯一规则为 main；protection_rules 只能包含 branch_policy，不得包含 Required reviewers、Wait timer 或其他外部审批规则；不要选择所有受保护分支。
4. Environment secret：PRP_COLLAB_APP_PRIVATE_KEY。
5. Environment variables：
   - PRP_COLLAB_APP_CLIENT_ID：专用 GitHub App Client ID。
   - PRP_COLLAB_APP_ID：5561446。
   - PRP_COLLAB_RULESET_ID：26294671。
6. 专用 GitHub App 安装到 micor-cjj-spec/matrix-prp。Issue 工作流通过 owner 和 repositories 输入，将每次 installation token 限定到 matrix-prp，并在写入前再次验证 token 可访问的仓库清单。
7. 不给协作 App main bypass；保留 main Ruleset #24968649 和生产发布冻结。

旧 prp-collab-controller Environment 与手动协调器保留为独立旧路径，不作为日常任务操作的审批入口。不要为了启用零点击操作而删除 main 或状态分支保护。

## 只读检查内容

activation-preflight.mjs 检查：

- main 和状态分支均受保护；
- main Ruleset #24968649 处于 active、目标为默认分支且没有 bypass actors；
- 状态 Ruleset 精确匹配 prp-collab-state，且唯一 bypass 是指定 Integration App；
- 正式状态仍是固定 V0 SHA，版本为 0、五个任务均 READY、无领取和请求账本记录；
- prp-collab-automation 不含 Required reviewers / Wait timer，部署分支策略仅允许 main；
- Environment secret 名称和三个变量存在且值匹配；
- 专用 App installation token 的可访问仓库只有 micor-cjj-spec/matrix-prp；
- main 的 publication-hold.json 存在且有效。

任何 API 不可读、环境不匹配、规则不可见或状态偏移都会返回 NO_GO。检查脚本不会自动修复配置。

运行此脚本必须使用仓库管理员身份，以便读取完整的 Ruleset bypass_actors 列表。运行时的专用 App token 不授予 Administration 权限，GitHub 可能只向它返回 current_user_can_bypass；因此必须在启用前和每次 Ruleset 变更后，通过管理员 preflight 独立确认完整列表恰好只有 App 5561446。不要给协作 App 增加 Administration 权限。

## 运行方式

在可信管理员工作站使用 GitHub CLI 登录仓库管理员账号，确保本地已取得状态分支 commit 对象：

```bash
git fetch --no-tags origin refs/heads/main
git fetch --no-tags origin refs/heads/prp-collab-state
export PRP_COLLAB_APP_ID='5561446'
export PRP_COLLAB_RULESET_ID='26294671'
# 仅在受控临时环境提供短期、单仓库 App installation token；不要写入脚本或提交历史
export PRP_COLLAB_APP_TOKEN='短期单仓库安装令牌'
node app/scripts/dev-collab/activation-preflight.mjs
```

脚本只检查 secret 名称，不读取或输出私钥值。不要把私钥或 Token 粘贴到 ChatGPT、Issue、仓库文件或 Actions 日志。

## 结果含义

- PRECONDITIONS_OBSERVED：可观察前置条件全部满足；仍不代表任务写入已经授权。
- NO_GO：存在阻断项，禁止执行试点写入。

即使返回 PRECONDITIONS_OBSERVED，也始终返回 allow_claim=false、allow_merge=false、allow_deploy=false。真实试点必须由用户在 ChatGPT 中明确发起 owner-authored Issue 请求，并以 Actions 成功回执和远端状态 SHA 为准。

V0→V1 迁移也必须由用户在 ChatGPT 中明确要求执行。普通“继续 PRP”或领取任务请求不代表迁移授权。
