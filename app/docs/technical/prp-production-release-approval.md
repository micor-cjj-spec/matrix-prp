# PRP 候选构建、只读验收与手动生产发布

main CI 成功仅自动构建候选包，**不会自动执行 publish、数据库迁移或应用切换**。即使运行名称含 auto-deploy 且结果绿色，也不能当作生产部署成功。

## 环境和权限

保留现有 production 环境保护规则及审批设置，不为诊断取消审批或增加分支权限。部署分支仅允许 main。PRP_DEPLOY_HOST、PRP_DEPLOY_KNOWN_HOSTS、PRP_DEPLOY_SSH_KEY 仍使用现有 production Environment secrets，不复制或公开其值。主分支规则、必需 CI、禁止强推及禁止绕过保护均保留。

发布和只读验收共用 prp-production 并发锁。专用密钥只调用受限网关，不得授予通用 shell、SFTP、转发或任意 sudo。原控制器数据保护不可关闭。

## 本次只读验收

1. 合并后等待 main CI 全绿，确认自动候选工作流的 publish 为 skipped。
2. 仅在已获授权时手动运行 PRP read-only SSH acceptance，分支选择 main。
3. 查看 Step Summary 和 prp-readonly-ssh-evidence artifact。该动作不备份、迁移或切换应用。
4. 认证、host key、网络、超时、未知错误或请求成功均不能作为拒绝通过证据。
5. 本次授权到只读验收结束，数据库须保持 V17；正式 V19 发布另行批准。

## 正式发布（需要后续单独授权）

Deploy PRP 的手动默认动作是 build，不是生产发布。只有获得正式发布授权后，才可选择 deploy（重新构建并发布），或 promote（使用同一 main SHA 的成功候选 run ID）。build 或只读检查成功不代表获准发布。

publish 必须仅由 main 上的 workflow_dispatch 触发。源提交、发布包和 main 最新 SHA 一致，控制器 SHA 与清单一致，真实 SSH 门禁全通过，才能进入既有备份、恢复预演、数据完整性校验、迁移和切换流程。

完成后须独立核对生产提交、Flyway 成功版本、历史数据保护、systemd、HTTPS 和核心接口。门禁失败必须停止，不得跳过、反复触发部署、强制修改 Flyway 或恢复旧数据。跨数据库版本不自动回滚，由运维根据实际阶段审查处理。

生产 SQL 备份保存在服务器本地，不能替代独立备份及恢复演练；本次不备份视频文件。
