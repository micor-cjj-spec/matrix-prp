# PRP 受保护自动发布与生产验收

在真实 V19 发布、无损数据和 SSH/SFTP 门禁验收通过后恢复 main 自动发布。
只有本仓库 main push 的完整 CI 成功、候选 build 成功，才允许 workflow_run
进入 production 发布任务。PR、fork、其他分支、失败/取消/未知 CI 和 build
失败都拒绝。保留手动 build/promote/deploy/check/rollback；手动默认 build。

## 保持的保护

- production 环境原有分支限制、审批及 secrets 不变；只允许 main。
- 源 CI、候选、受测提交、最新 main 必须一致；过期提交拒绝。
- SSH 私钥只在环境任务中短暂使用，固定 known_hosts、专用 prp-deploy 身份。
- 每次正式发布重新验证实时 nonce 策略、精确 SFTP INIT 拒绝、实际 subsystem INIT、shell/注入及双向转发拒绝；控制器 SHA 必须匹配清单。
- 既有数据库备份、隔离恢复迁移、完整历史内容指纹、切换前备份、Flyway validate、健康及认证业务检查全部保留。
- 只读验收工作流保持 main-only、只读权限和固定探测，不调用发布入口；与发布共享 prp-production 并发锁。
- 原始 SQL、配置、token、密钥和 root 日志不上传 artifact；失败仅上传脱敏诊断。

SSH helper 升级或策略基线变化需要独立安全审查，禁止从候选 JSON 自动批准。
用户在 2026-10-17 明确授权本次后续备份、预检、V19 发布、验收和自动发布恢复。
此授权不代表未来可以放宽现有 production 环境和权限保护。

## 失败恢复边界

在线预检失败时不切换应用或修改生产 schema。切换前停止写入并再做完整备份和
历史指纹快照。生产 schema 已变化时不得自动恢复旧 SQL 或回退旧应用；既有
控制器会拒绝跨 schema 自动回滚并保留备份，管理员需按实际阶段审查，避免覆盖
用户新数据。相同 schema 的应用回退继续使用受限 rollback。

## 验证自动发布

恢复补丁的 PR 完整 CI 通过后，先确认 V19 手动正式发布及业务验收成功，再合并。
随后必须观察这次 main push → CI → 自动 build → publish → 实际健康验收成功，
并核对 current/release.json commit 与合并 main 一致，不能只凭配置或绿色 CI 宣布恢复。
自动发布守卫测试直接评估实际 job 条件，覆盖可信 main、PR、fork、分支、失败/未知
CI、build 失败和手动动作矩阵；正式验收仍以真实运行结果为准。

数据库 SQL/配置备份仅保存在 root-only 目录；这不替代独立视频备份和异地灾备。
