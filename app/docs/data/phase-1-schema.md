# Phase 1 Schema

一期把结构化个人数据存入 MySQL，同时继续保留 `knowledge/` Markdown 知识库作为文件资产。

## 表清单

| 表 | 用途 |
| --- | --- |
| `prp_records` | 通用记录，覆盖工作、生活、学习、社交、兴趣等领域。 |
| `prp_tags` | 通用标签字典。 |
| `prp_record_tags` | 记录和标签的多对多关系。 |
| `prp_tasks` | 个人任务和下一步行动。 |
| `prp_finance_transactions` | 收入和支出流水。 |
| `prp_reviews` | 周、月、模块级复盘。 |

所有用户业务表都包含 `user_id`。一期先按单用户使用，后续可升级到多用户、家庭或团队模式。

后端会对任务优先级、任务状态、财务流水类型和复盘类型做枚举校验，防止客户端写入未约定值。

## 表说明

### prp_records

关键字段：

- `module_code`: 所属领域模块，例如 `life`、`learning`、`work`。
- `title`: 记录标题。
- `content`: 记录内容。
- `record_date`: 记录日期。

主要索引：

- `idx_prp_records_user_created`
- `idx_prp_records_module_date`

### prp_tags

关键字段：

- `name`: 标签名称，同一用户下不允许重复未删除标签。
- `color`: 标签颜色。
- `description`: 标签说明。

主要索引：

- `uk_prp_tags_user_name_deleted`
- `idx_prp_tags_user_created`

### prp_record_tags

关键字段：

- `record_id`
- `tag_id`

主要约束：

- 同一记录不能重复绑定同一标签。
- 删除记录或标签时，关系记录级联删除。

### prp_tasks

关键字段：

- `module_code`: 所属领域模块。
- `priority`: `low`、`medium`、`high`。
- `status`: `todo`、`in_progress`、`done`、`canceled`。
- `due_date`: 截止日期。
- `completed_at`: 完成时间。

主要索引：

- `idx_prp_tasks_user_status_due`
- `idx_prp_tasks_priority_due`
- `idx_prp_tasks_module_created`

### prp_finance_transactions

关键字段：

- `type`: `income` 或 `expense`。
- `amount`: 金额，`DECIMAL(18,2)`。
- `category`: 一期使用字符串分类。
- `account`: 一期使用字符串账户。
- `merchant`: 商户或对象。
- `transaction_date`: 交易日期。

主要索引：

- `idx_prp_finance_user_date`
- `idx_prp_finance_type_date`
- `idx_prp_finance_category_date`

### prp_reviews

关键字段：

- `review_type`: `weekly`、`monthly`、`module`。
- `module_code`: 关联领域模块。
- `summary`
- `highlights`
- `problems`
- `next_actions`
- `period_start`
- `period_end`

主要索引：

- `idx_prp_reviews_user_period`
- `idx_prp_reviews_type_module`

## 初始化

本地 MySQL 由下面脚本初始化：

```text
app/docker/mysql/init/001-schema.sql
```

通过 Docker Compose 启动：

```powershell
cd app/docker
docker compose up -d
```

MySQL 初始化脚本只会在数据卷首次创建时自动执行。开发过程中如果表结构变化，需要手动应用 SQL，或在确认可丢弃本地数据后重建数据卷。
