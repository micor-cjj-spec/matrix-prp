# PRP 一键部署

生产地址：https://micor.top/prp/ 。保持 Java 21 systemd + Nginx，数据库仍在现有 Docker 容器中。

## 日常发布

1. 合并代码到 `main`。
2. 等待同仓库 `main` push 的完整 CI 成功，随后自动构建并进入受保护的生产发布任务。
3. 保留 `production` 环境现有审批要求；有审批时等待批准。SSH/控制器/产物/数据门禁必须全部通过。
4. 查看 publish 实际成功、发布摘要、版本 ID 和生产运行提交；CI 或 build 绿色不能代替上线验收。

PR、fork、分支 CI、失败/取消的 CI 不会自动发布。手动入口仍默认 `build`；`promote` 使用同一最新 main SHA 的成功候选 run ID，`deploy` 重新构建并发布，`check` 只检查生产，`rollback` 需要服务器已有且数据库版本一致的 release ID。自动发布失败后先查脱敏诊断，不得跳过门禁。

## 发布流程

- GitHub 执行后端单元测试、真实 MySQL 业务隔离测试、不可变迁移检查、部署边界测试、前端类型检查和构建。
- Maven/npm 依赖缓存；构建产物保留 14 天。生产使用 `/prp/`，API 和视频使用 `/prp/api/`，避免与主站 Matrix `/api/` 冲突。
- 通过专用 SSH 账户 `prp-deploy` 将带 SHA256 清单的产物传给固定发布入口。该密钥不允许交互 Shell、SFTP 或端口转发。
- 服务器串行发布，保留运行配置，备份数据库，在隔离库实际恢复并验证迁移，再用 Flyway 追加生产迁移。
- 发布目录 `/srv/matrix-prp/releases/<release-id>`；`current` 指向当前版本，Nginx 和 systemd 从此读取产物。
- 只有前端源码变化时保留旧后端 JAR，不执行数据库迁移或重启后端。
- 检查健康、账户接口、题库、健康中心、PWA 和全部私有视频文件，并抽样验证 206 视频播放。

## 数据库与回退

历史数据库必须先由管理员备份、实际恢复、对比完整 V1–V7 表定义，再显式登记 V7 基线；日常 SSH 发布入口不能执行基线登记。

Flyway 禁止自动 baseline、clean 和未解释的 repair；数据库密码只通过受保护的 stdin 传给迁移工具，保留在服务器。

`rollback` 只允许回退到与当前数据库版本一致的应用版本，不恢复旧数据库，也不删除视频。
迁移失败但数据库版本未改变时恢复旧应用；数据库已经推进时停止自动回退，由管理员检查，防止掩盖部分 DDL 或覆盖新增用户数据。

第一次从老版本跨数据库版本升级后，旧应用暂不能通过按钮回退；需明确评估数据库兼容性。
后续同一数据库版本的发布可以直接选择已有版本回退。

## 位置和权限

- 备份：`/root/prp-deploy-backups/<release-id>`；只允许 root 读取。
- 发布锁及失败详情：`/var/lib/matrix-prp-deploy/`；错误详情不会直接打印到 Actions。
- 固定服务器程序：`/usr/local/sbin/prp-release`；SSH 网关：`/usr/local/bin/prp-deploy-gateway`，均 root 所有。
- 应用仍以 `openclaw` 运行；配置 `/etc/matrix-prp/application.yml` 和视频 `/srv/matrix-prp/video` 保持独立。
- GitHub `production` 环境仅允许 `main` 发布，Secrets 是专用 SSH 私钥、固定 known_hosts 和服务器地址，不包含 root 密码或数据库密码。

部署脚本改变后，须由管理员审核并更新服务器上的固定程序；普通产物不会替换 root 程序。
不要自动删除备份或旧版本，维护时按空间和保留策略清理。应用备份不代替视频备份；现有课程源文件及 SHA256 清单继续保留。
