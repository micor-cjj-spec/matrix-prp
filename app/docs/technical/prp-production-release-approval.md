# PRP 生产环境发布审批（公开仓库）

## 现有实现与安全边界

`deploy-prp.yml` 的候选发布阶段由 main 分支的 **CI push 成功**事件启动，执行测试、独立 MySQL 验证并上传 `prp-release`，**不会自动访问生产 SSH**。发布操作仍必须显式启动 `workflow_dispatch` 并选 `promote`，输入候选运行 ID。此为私有仓库时的安全兼容方案，尚不是原生 GitHub「等待审批后立即发布」的单次流程。

公开仓库可进一步升级成原生 `production` 环境 Required reviewers 审批；只有 GitHub 账号管理员配置好环境审批和分支保护后，才应启用自动进入环境的 `publish` job。**不要**在 GitHub Environment 未设置 required reviewers 时，仅靠声明 `environment: production` 就自动执行 SSH 部署。

## 必须先由管理员在 GitHub 网页设置

1. 打开仓库 **Settings → Environments → production**。存在就编辑，不存在则创建。
2. 启用 **Required reviewers**，明确选择审批人；如只有一位管理员负责审批，勿同时开启 `Prevent self-review`。建议启用 `Disallow admin bypass`（如果界面支持）。
3. **Deployment branches and tags** 设为 **Selected branches and tags**，仅允许 `main`（不要选择 `No restriction`，也不要在尚无分支保护时误用 `Protected branches only`）。
4. 检查 `production` **Environment secrets** 仅有以下部署凭据：`PRP_DEPLOY_SSH_KEY`、`PRP_DEPLOY_KNOWN_HOSTS`、`PRP_DEPLOY_HOST`。确保这些值并未写在仓库源码、Issue、PR 或日志中。移除不再需要的 repository-level 同名部署 secrets。
5. 设置 **Settings → Branches** 或 **Rules → Rulesets** 保护 `main`：必须 PR、必须通过 CI 对应的后端/Web/移动/数据库 checks，禁止 force push / delete，避免无审查直接修改工作流。保护规则的生效情况须在 GitHub UI 验证。

GitHub App 本次连接无法读取或修改环境审批设置，**本仓库的环境保护配置是否完成需要管理员在 GitHub 页面自行核实**。

## 候选包发布（当前可运行流程）

1. 合并获批 PR 至 `main`，等待 **CI** 的 main push 检查全部通过。
2. **Deploy PRP** 将通过 `workflow_run` 自动构建、上传候选 `prp-release`。从发布任务 Summary 复制当前 **candidate run ID**。
3. 人工检查本次提交、数据迁移清单和候选包 SHA。
4. 打开 **Actions → Deploy PRP → Run workflow**：选择 `main`，`action=promote`，`candidate_run_id=` 对应的已成功候选 Run ID。选中的候选 SHA 必须与当前 main 相同。
5. GitHub `production` 环境若配置了 Required reviewers，发布 job 会再次等待审核；审查通过后才解锁环境密钥并运行服务器发布网关。
6. 发布进程先校验备份与隔离数据库恢复、模拟迁移和行数/视频归属，再更换版本。Java 后端改变才重启 `matrix-prp.service`；发布后执行 `/api/health`、已认证接口、PWA 和私有视频验证。
7. 失败回退：仅当数据库版本与表结构仍兼容时，服务器脚本自动恢复上一应用版本。**数据库已经升级后禁止自动回滚到旧 schema**，须按 root-only 日志由运维处理。

## 发布操作限制

- `workflow_run` 必须来自仓库的 main push、CI 成功；不要接受 pull_request 或 forks 的工作流结果。
- `publish` 不应读取来自 PR 的任意可执行脚本或由用户上传的外部 tarball，必须验证候选运行状态、来源和 SHA。
- 同一时间只能运行一个 PRP 生产发布；发生较新 main 提交时旧候选不得覆盖新版本。
- `check` 和 `rollback` 属于生产操作，也应使用环境审查和受限部署账户。
- 不允许任意 root SSH、自动恢复旧数据库、上传明文生产凭据、自动批准自己的 PR。
- 生产备份默认保存在服务器内；若服务器只有单块磁盘，该备份**不具备灾难恢复能力**，建议以后独立配置异地加密备份。

## 未来原生升级

在确认 `production` Required reviewers/branch policy 生效后，可把候选 CI 任务的 `publish` 作业调整为 **`needs: build`、`environment: production`**，审核通过后直接使用同次运行的候选包。上线前必须增加自动化的 fail-closed 环境保护校验和一次真实的「待审核 → 拒绝 → 重新审核批准」演练，避免环境配置遗漏时无审核自动上线。

GitHub 参考：
- https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments
