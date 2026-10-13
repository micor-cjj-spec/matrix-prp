# PRP 无人值守自动部署（公开仓库）

## 发布模式

管理员明确选择 **CI 成功后自动发布生产环境**：不再要求每个版本点击 `Approve and deploy`。

```
开发分支 → PR → 必需 CI 全绿 → Squash 合并 main
→ main CI 成功 → Deploy PRP（workflow_run）
→ 重新构建+独立 MySQL 集成验证
→ 校验源 SHA 与 main 一致 → 受限 SSH 发布
→ 自动备份/迁移检查 → 按需重启 matrix-prp.service → 健康检查
```

现有 `.github/workflows/deploy-prp.yml` 仍支持手动 `deploy`、`check`、`rollback`、`build`，以及旧版候选包 `promote`。发布作业继续使用 `production` 环境 Secrets 和唯一的 `prp-production` 并发锁，不使用通用 SSH shell 或 root Token。

### 唯一需要由管理员执行的设置

进入 **Settings → Environments → production**：

1. **取消勾选 Required reviewers，保存保护规则。** 不取消就仍然会停在 `Approve and deploy`，这是 GitHub 的保护行为，工作流不会绕过它。
2. 保持 Deployment branches and tags = **Selected branches and tags**，**只允许 main**。
3. `PRP_DEPLOY_HOST`、`PRP_DEPLOY_KNOWN_HOSTS`、`PRP_DEPLOY_SSH_KEY` 均保留为 `production` Environment secrets；勿将真实值粘贴到 Issue、工作流 YAML、聊天或 PR。
4. **main Ruleset `protect-main` 必须保持 Active**，要求通过 PR、6 项 CI 全绿、禁止 force push 和删除分支，并且 Bypass list 为空。

关闭生产部署审批意味着：只要有权提交经允许的 PR 并满足主分支规则，就能导致生产自动部署。若以后多人参与，建议恢复生产审批，或采用仅对数据库/鉴权/部署基础设施变更要求人工审核的策略。

## 自动发布的安全前置条件

- `workflow_run` 仅接受 **本仓库主分支 push** 触发的 **CI 成功**；PR、fork 或失败的 CI 不得发布。
- 构建独立完成后才允许 `publish`，而且 `publish` 限定 main。
- 自动发布获取的构建包 `release.tar.gz` 内的 commit 必须与通过 CI 的 `main` 提交一致，发布前再次查询 main 最新 SHA；旧提交不能覆盖新版本。
- `production` 下的专用密钥只在 `publish` 使用；服务器受限 SSH gateway 仅支持 deploy/check/rollback/status。
- `app/deploy/server-release.py` 保留数据库完整备份、恢复验证、Flyway 迁移预演、数据行数及私有视频校验，非兼容数据库版本**不自动回滚**，由运维审查后处理。
- 服务器备份位于本地磁盘，无法替代异地备份；请配置加密异地备份以免单盘故障导致数据丢失。

## 验收步骤

1. 合并工作流 PR 后，在 Actions 页面观察 `CI` main 检查全部绿色。
2. GitHub 自动新增一次 **Deploy PRP · auto-deploy** 运行，先执行 build，成功后自动执行 publish；无需再输入候选 run ID。
3. `publish` 完成后检查其 summary、服务器 release SHA、HTTPS `/prp/`、登录、AI 对话、PWA、视频和数据是否正常。
4. 如果仍显示 `Waiting for review`，检查 `production` 是否遗留 Required reviewers；不要通过绕过保护按钮规避。
5. 如 Actions 报错、服务器停止或数据库已迁移，**不要反复触发部署或恢复旧数据**，先查看 CI/运维日志并确认兼容性。

GitHub 环境参考：
- https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- https://docs.github.com/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments
