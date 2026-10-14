# PRP P0 异机加密备份与隔离恢复操作手册

> 适用生产：单台 Linux + systemd 服务 `matrix-prp` + Docker 容器 `matrix-mysql` + Nginx，本地视频目录 `/srv/matrix-prp/video/media`。本功能是**需管理员显式安装、配置与启用**的独立数据保护通道；普通 PR 合并、Actions 发布和既有受限 SSH 网关不会安装它，也不会代填密钥。

## 设计边界

- **远端**：采用 Restic + HTTPS S3 兼容存储，Restic 在发往对象存储前加密并进行去重，密钥不进入应用数据库、GitHub 或构建产物。不得把目的地放在生产机同一磁盘、同一故障域，也不得使用未加密的 HTTP。
- **密钥分离**：Restic 密码文件与 S3 凭据文件从备份中显式排除，必须另外放在独立密码管理器中，并由至少一名授权恢复管理员验证能在异机安全取回；否则远端快照可能无法解密恢复。
- **内容**：每次生成 MySQL `matrix_prp` 一致性逻辑转储（`--single-transaction`），备份 `/etc/matrix-prp`、`/etc/nginx/snippets/matrix-prp.conf`、`/srv/matrix-prp/video/media`，存在时附带 `/srv/matrix-prp/knowledge`。配置包含秘密，只能存入加密仓库。
- **验证**：对数据库转储执行 SHA256、记录 Flyway Schema 版本、对视频文件路径和大小做清单指纹。Restic 对远端仓库执行 metadata `check`。这些不等于远端**全部数据**可恢复；月度恢复演练必须真实下载、验证和导入。
- **一致性范围**：数据库快照和视频文件不是跨资源原子快照。视频上传/删除期间，若视频数量、文件名或大小变更则失败并告警；极端的同大小原地改写依然不能完全排除。建议安排低活动时段，确保已完成上传的视频采用不可变文件策略。
- **磁盘占用**：只在 `/var/lib/matrix-prp-backup` 暂存一个 MySQL SQL 文件；Restic 原始视频直接从现有目录读取，不复制整个视频库到本地磁盘。任务结束后删除 SQL 暂存文件。
- **失败告警**：备份前强制要求已配置 HTTPS webhook；systemd `OnFailure` 会将静态严重故障提示送到通知端点。必须对该端点进行真实送达测试，不能仅看日志认为告警成功。

## 一、管理员安装（仅在核准的生产服务器上操作）

准备独立的 S3 私有桶、受限访问凭据、Webhook 通知地址，并在云存储侧设置账户保护、访问日志和版本化/不可变保护策略。备份远端具有与生产主机不同的故障域和访问控制。

1. 在服务器安装 `restic`，确认 Docker、Python3、systemd 可用，备份脚本固定来源为已评审的仓库提交。
2. 核验脚本源码及 SHA256 后，将 `app/deploy/prp-offsite-backup.py` 安装为 `/usr/local/sbin/prp-offsite-backup`，属主 root，权限 `0750`；不要将其添加到现有 `prp-deploy` SSH 网关授权列表。
3. 将 `app/deploy/systemd/prp-offsite-backup.service`、`prp-offsite-backup-alert.service`、`prp-offsite-backup.timer` 复制至 `/etc/systemd/system/`，属主 root。
4. 在生产服务器 root shell 中配置以下 root-only 文件：

```bash
install -d -m 0700 -o root -g root /var/lib/matrix-prp-backup
umask 077
test -e /etc/matrix-prp/restic-password || touch /etc/matrix-prp/restic-password
test -e /etc/matrix-prp/backup.env || touch /etc/matrix-prp/backup.env
chown root:root /etc/matrix-prp/restic-password /etc/matrix-prp/backup.env
# 在服务器上安全填充随机的 Restic 密钥，以及 backup.env 中的远端凭据/告警地址。
# 仅将 app/deploy/systemd/prp-offsite-backup.env.example 作为字段模板，绝不要使用里面的占位值。
chmod 0600 /etc/matrix-prp/restic-password /etc/matrix-prp/backup.env
```

配置 `backup.env` 的字段：`RESTIC_REPOSITORY=s3:https://独立域名/私有桶/prp`、`RESTIC_PASSWORD_FILE=/etc/matrix-prp/restic-password`、`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY` 和 `PRP_BACKUP_ALERT_WEBHOOK_URL`（HTTPS 私有告警端点）。**不要**提交真实值，不要用 GitHub Actions artifact、Issue、聊天或日志传送密钥。

5. 首次仅由管理员使用同一组环境变量执行一次 `restic init` 初始化私有仓库，确认 TLS 证书和远端访问控制正确。不要在定时服务中自动初始化仓库。
6. 验证远端与源目录（执行时需带入 root-only 环境变量）：

```bash
set -a
. /etc/matrix-prp/backup.env
set +a
/usr/bin/python3 /usr/local/sbin/prp-offsite-backup preflight
# 仅向预先配置的私有通知端点发送静态测试消息（务必确认收到）
/usr/bin/python3 /usr/local/sbin/prp-offsite-backup alert-failure
systemctl daemon-reload
systemctl start prp-offsite-backup.service
systemctl status prp-offsite-backup.service --no-pager
# 确认远端确实有新快照、数据库快照元数据与视频列表
restic snapshots --tag matrix-prp
systemctl enable --now prp-offsite-backup.timer
systemctl list-timers prp-offsite-backup.timer
```

**注意**：命令 `. /etc/matrix-prp/backup.env` 仅在该文件由可信 root 管理、内容经过审查时执行，严禁直接执行不可信环境文件。命令完成后退出该 root shell，避免泄露凭据到后续进程。

## 二、每日与每月验收

每日确认 timer 最近完成时间、service 最后结果、Restic 远端快照是否出现，以及Webhook是否可达。备份服务失败必须通知真人，解决后手动重试并复核快照。

每月在与生产服务器隔离的恢复主机上，用临时的、最小权限的恢复凭据运行：

```bash
# 恢复主机：只读方式连接同一加密仓库，使用经过授权取得的 Restic 密码
restic snapshots --tag matrix-prp
mkdir -m 0700 /srv/prp-restore-sandbox
restic restore latest --tag matrix-prp --target /srv/prp-restore-sandbox
# 在恢复主机上运行该版本对应的校验脚本：
python3 prp-offsite-backup.py verify-restored --target /srv/prp-restore-sandbox
# 检查通过后，仍必须从恢复出的 SQL 向隔离的 MySQL 实例真实导入数据，
# 再执行用户、会话、健康、财务、视频鉴权、Range 播放及 Flyway 版本的测试。
```

数据库 SQL 的位置为 `/srv/prp-restore-sandbox/var/lib/matrix-prp-backup/backup-*/matrix_prp.sql`。恢复主机必须先验证完整文件 SHA256，然后使用独立 MySQL 实例导入，切勿向生产 `matrix_prp` 直接导入。恢复后应核实快照用户数、会话数、餐次数、财务流水数、427 个视频等实际数量；427 只是 2026-10-14 的历史值，后续以快照清单为准。

`restic check` 默认检查元数据完整性，月度验收需在恢复主机额外执行 `restic check --read-data` 或逐项完整恢复来验证远端数据包。

## 三、保留策略与验收标准

- **凭据安全**：远端快照包括敏感业务配置但不包括 Restic 密码文件或 S3 凭据文件。异机恢复必须从独立密钥库恢复这些秘密，不得从备份仓库反向获取。
- **建议起点**：保留最近 7 份每日恢复点、4 份周恢复点、3 份月恢复点。Restic `forget --tag matrix-prp --keep-daily 7 --keep-weekly 4 --keep-monthly 3` 和 `prune` 仅由管理员在恢复演练成功、远端生命周期策略审查后单独执行；初始版本不自动删除任何远端数据。
- **建议目标**：RPO ≤ 24 小时、RTO ≤ 4 小时；只有在真实故障模拟、隔离恢复演练和告警送达验证完成后才能对外声明达标。
- **禁止**：直接覆盖生产库、还原恢复时清空生产视频、给 GitHub Actions 配置 MySQL root/Restic/S3 密钥、把私有文件打包进 Release/Artifacts、绕过发布权限保护。
- **证据**：保存恢复快照 ID、SHA256 校验、MySQL schema 版本、验证用例结果、时长、执行人、告警送达记录。证据中不得包含 SQL 数据、JWT 或密钥。
- **限制**：自动发布的在线备份和本脚本各自独立运行；新增脚本不代表服务器已经安装定时任务。必须由管理员显式确认安装以及异地备份与恢复验收结果。
