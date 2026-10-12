# 健康中心食物名称乱码：排查与无损修复

## 现象、范围和原因

在“健康中心 → 新增餐次 → 搜索食物”中，内置食物如“土豆（87 kcal/100g）”“米饭（116 kcal/100g）”出现类似乱码。原始 V7 SQL、Vue 模板与 API 均包含正确 UTF-8 中文，因此**优先怀疑历史 SQL 通过 latin1/非 UTF-8 客户端导入时写入了错误字符串**；不应靠前端猜测编码修复数据库。

V12 `app/backend/src/main/resources/db/migration/V12__repair_legacy_food_seed_encoding.sql` 对原始 V7 的 **9 条内置食物**实施严格匹配的定向修复：
- 只更新 `owner_user_id IS NULL`，且名称等于预期“UTF-8 被当成 MySQL latin1 解码”的字符串、烹饪方式及全部营养值与原始种子一致的条目。
- 内置食物 `source_note` 仅在仍等于对应乱码原文时修改；不会覆盖后来编辑的说明。
- 仅对关联已确认内置食物、原有快照名称也仍是对应乱码的 `prp_wellness_meal_items.food_name` 更新。保留餐次、食物 ID、数量、营养值、用户关联。
- 通过十六进制 UTF-8 常量和 MySQL 字符集转换完成对照，脚本可重复运行；没有 `DELETE`、`TRUNCATE`、重建表或修改用户私有食物。
- V1–V7 已发布的迁移和 Docker 初始化脚本保持完全不变，维护 Flyway 校验值。

## 生产环境执行顺序（**不要仅凭合并就认为已有数据被修复**）

1. 确认数据库连接到的是 PRP 的 `matrix_prp`，核对 MySQL 客户端/服务端/表的字符集。先查询：

   ```sql
   SHOW VARIABLES LIKE 'character_set%';
   SHOW CREATE TABLE prp_wellness_foods;
   SELECT id, name, HEX(name) AS name_hex, preparation, calories_100g, source_note
     FROM prp_wellness_foods WHERE owner_user_id IS NULL ORDER BY id;
   ```

2. 停止写入，做好 **可恢复的** MySQL 备份（保留到其他安全存储位置，尤其只有一个服务器磁盘时），并在独立数据库测试恢复：

   ```bash
   mysqldump --single-transaction --routines --triggers --events \
     --default-character-set=utf8mb4 -h "$DB_HOST" -u "$DB_USER" matrix_prp \
     > matrix_prp.before-encoding-repair.sql
   ```

   密码通过受保护的环境变量或交互输入，不放进命令参数、仓库或日志。务必记录修复前内置食物与餐次的数量、ID 和抽样。

3. **已完成 Flyway 旧库基线且 `MATRIX_PRP_FLYWAY_ENABLED=true`**：部署后由 Flyway 按版本执行 V12，确认 `flyway_schema_history` 为成功，并复查数据。

   **Flyway 仍关闭（项目默认）**：在验证备份和 SQL 变更后，通过 UTF-8 客户端手工执行 V12 一次，**不要**仅重启 Java 就期待迁移运行：

   ```bash
   mysql --default-character-set=utf8mb4 -h "$DB_HOST" -u "$DB_USER" matrix_prp \
     < app/backend/src/main/resources/db/migration/V12__repair_legacy_food_seed_encoding.sql
   ```

   后续如果正式启用 Flyway，原有基线操作按 `safe-db-migrations-p0.md` 执行；V12 具有幂等性，Flyway 可以安全重复检查。**不要**对已有旧库开启自动 baseline、执行 `clean`、删除 Docker 卷或回改 V7。

4. 重查步骤 1 的食物数据，再核对已经保存的餐次名称：

   ```sql
   SELECT i.id, i.food_id, i.food_name, i.grams
     FROM prp_wellness_meal_items i
     JOIN prp_wellness_foods f ON f.id=i.food_id
    WHERE f.owner_user_id IS NULL ORDER BY i.id DESC LIMIT 30;
   ```

   核对数据总行数和历史餐次热量不变，再在 iPhone PWA 中关闭弹窗、重新打开健康中心或刷新页面。代码部署与数据库执行是两个不同操作。

## 排查其他模块

- `node app/scripts/check-text-encoding.mjs`：静态检查 Web、移动端、Java 与 SQL 等文本源码的 UTF-8 合法性和典型乱码模式。它不会连接生产数据库。
- 在数据库中检查非 UTF-8 的文本字段，并确认实际连接使用的字符集：

  ```sql
  SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_SET_NAME
    FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE() AND CHARACTER_SET_NAME IS NOT NULL
     AND CHARACTER_SET_NAME NOT LIKE 'utf8mb4%'
   ORDER BY TABLE_NAME, ORDINAL_POSITION;
  SHOW VARIABLES LIKE 'character_set_connection';
  SHOW VARIABLES LIKE 'character_set_client';
  ```

- 业务层还需要抽样检查任务/记录、财务、通知、视频、题库、AI 会话等用户数据中的中文（尤其历史导入记录）。**仅凭源码扫描不能证明现有生产数据库所有字段都没有乱码**，发现其他数据异常应在隔离副本上先确认编码路径，再创建独立、可回滚的定向迁移；切勿使用全库 `CONVERT(... USING latin1)` 批量覆盖。

## 防止再次发生

- MySQL 命令行导入 SQL **显式增加 `--default-character-set=utf8mb4`**；CI 导入已固定此选项。
- Java 默认 JDBC URL 使用 `characterEncoding=UTF-8&connectionCollation=utf8mb4_unicode_ci`。如线上通过 `MATRIX_PRP_DB_URL` 覆盖，必须逐项检查实际 URL（切勿展示密码）。
- HTML 已声明 UTF-8。Web 端不应通过重新编码 API 文本来掩盖库内错误。
- CI 同时验证 V1–V7 不变、V12 修复乱码后 ID/营养数据及用户数据不变，并对源码执行编码检查。
