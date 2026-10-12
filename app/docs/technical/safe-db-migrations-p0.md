# P0：数据库版本管理、无损切换与回滚

## 基本原则

- 不删除、重建或清空任何现有数据卷。本 PR 不操作生产数据库。
- 既有 app/docker/mysql/init/001..007 保持不变；Flyway V1..V7 与原始 SQL 逐字节一致。
- MATRIX_PRP_FLYWAY_ENABLED 默认 false。这是分阶段迁移开关，现有 systemd 服务升级程序后仍按原方式运行。
- baseline-on-migrate=false，clean-disabled=true。没有经过确认的老库不会在启动时被默认为完整 V7。
- 当库只应用了部分 001..007 时，绝对不能标记为 V7。前置检查仅核验表清单及关键字段，还必须人工检查自定义改动。
- V1..V7 一旦发布后禁止修改。AI 建表已迁至独立 V8；必须在完成已有 V1..V7 的显式旧库基线后执行 V8。

## 生产旧库：操作员顺序

1. 确认服务器、数据库连接与维护窗口，停止写入。记录当前运行版本与历史 SQL 执行记录。
2. 备份 MySQL、上传的视频目录与部署配置；推荐使用 MySQL 一致性备份：

       mysqldump --single-transaction --routines --triggers --events \
         --default-character-set=utf8mb4 matrix_prp > matrix_prp.before-flyway.sql

   不要将备份文件提交到 GitHub。必须在另一库实际恢复并确认数据可读取，保存关键表行数和样本 ID。
3. 按现场记录确认 001..007 完整应用；漏掉脚本时必须先备份，再按原脚本顺序补齐并验证业务。不要通过删除 Docker 数据卷重来。
4. 有 Node 22+ 和 mysql CLI 的环境中，设置 MYSQL_PWD 以及 MATRIX_PRP_DB_HOST / MATRIX_PRP_DB_PORT / MATRIX_PRP_DB_USER / MATRIX_PRP_DB_NAME，然后运行：

       node app/scripts/verify-db-migrations.mjs
       node app/scripts/verify-legacy-baseline.mjs

   两个检查只读；任意失败即停止升级。检查通过不代表架构与生产定制百分百一致。
5. 使用支持 MySQL 的 Flyway CLI，通过受保护的环境变量传入 FLYWAY_URL / FLYWAY_USER / FLYWAY_PASSWORD，设置 FLYWAY_LOCATIONS 为项目内 db/migration 文件夹的绝对 filesystem 路径，设置 FLYWAY_BASELINE_VERSION=7：

       flyway info
       flyway baseline
       flyway validate
       flyway migrate

   只执行一次 baseline；不得启用 baselineOnMigrate=true，不得使用 clean/repair 来消除未理解的差异。
6. 基线成功并验证后，为 Java systemd 环境设置 MATRIX_PRP_FLYWAY_ENABLED=true，重启后端。确认健康检查、账号、用户隔离、视频、通知、刷题和健康接口的数据仍正确。
7. 比较升级前后的关键表行数和业务数据；若发现问题，停止应用写入，按既定流程恢复已经验证过的备份及对应媒体文件，勿进行不受控的修复。

注意：Flyway 基线只登记当前版本，不会回放 V1..V7，亦不能替代真实备份。数据库凭据不要写入 GitHub、终端命令参数或 CI 日志。

## 全新空库

在没有任何旧表的空数据库中启用 MATRIX_PRP_FLYWAY_ENABLED=true，Flyway 自动按 V1..V8 创建表和版本记录。已有 Docker Compose 在新数据卷上会运行旧的 /docker-entrypoint-initdb.d 脚本：该老路径要保持 Flyway 关闭，或者另行创建不使用该初始化目录的空库。**不能**先运行 Docker 初始化脚本再将其当成全新 Flyway 数据库。

## 验证与上线限制

- verify-db-migrations.mjs 持续验证 V1..V7 历史镜像字节不变，并检查 V8 文件登记。
- 真实 MySQL CI 需分别检查新库迁移可重复、旧库显式 baseline 后数据不变。
- 服务升级默认不开启 Flyway，这避免用户服务器因缺失历史版本记录而启动失败，但生产正式切换仍需要运营操作。
- 登录防暴力尝试采用单实例内存限流；多实例部署还需要共享限流器或网关策略，反向代理传来的 X-Forwarded-For 不应未经信任配置就使用。
