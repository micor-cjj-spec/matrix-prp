# Data Model

## 设计原则

- 一期以单用户使用为主，但用户数据表保留 `user_id`。
- 通用能力优先建模，领域能力先在通用模型上扩展。
- 金额字段使用 `DECIMAL(18,2)`，避免浮点误差。
- 核心业务表保留 `created_at`、`updated_at` 和 `deleted` 软删除字段。
- 知识库一期仍以 `knowledge/` Markdown 文件为主，不先落知识库索引表。

## 核心实体

### User

一期使用固定开发账号，后续再落用户表和密码加密校验。

字段草案：

- `id`
- `username`
- `password_hash`
- `display_name`
- `status`
- `created_at`
- `updated_at`

### Module

模块用于区分功能模块和领域模块。一期模块由后端服务提供，暂不单独建表。

字段草案：

- `code`
- `name`
- `description`
- `type`: `feature` 或 `domain`
- `sort_order`
- `enabled`

### Record

通用记录承载生活、学习、工作、兴趣、社交、财务等模块的过程数据。

表：`prp_records`

- `id`
- `user_id`
- `module_code`
- `title`
- `content`
- `record_date`
- `created_at`
- `updated_at`
- `deleted`

### Tag

标签用于跨模块分类和记录筛选。

表：`prp_tags`

- `id`
- `user_id`
- `name`
- `color`
- `description`
- `created_at`
- `updated_at`
- `deleted`

### RecordTag

记录和标签的多对多关系。

表：`prp_record_tags`

- `id`
- `record_id`
- `tag_id`
- `created_at`

### Task

任务承载下一步行动。

表：`prp_tasks`

- `id`
- `user_id`
- `module_code`
- `title`
- `description`
- `priority`: `low`、`medium`、`high`
- `status`: `todo`、`in_progress`、`done`、`canceled`
- `due_date`
- `completed_at`
- `created_at`
- `updated_at`
- `deleted`

### FinanceTransaction

财务一期直接记录流水，不先拆账户表和分类表。

表：`prp_finance_transactions`

- `id`
- `user_id`
- `type`: `income` 或 `expense`
- `amount`
- `category`
- `account`
- `merchant`
- `note`
- `transaction_date`
- `created_at`
- `updated_at`
- `deleted`

### Review

复盘承载周、月、模块级回顾。

表：`prp_reviews`

- `id`
- `user_id`
- `review_type`: `weekly`、`monthly`、`module`
- `module_code`
- `title`
- `summary`
- `highlights`
- `problems`
- `next_actions`
- `period_start`
- `period_end`
- `created_at`
- `updated_at`
- `deleted`

### KnowledgeFile

知识库一期不建表，由后端读取 `knowledge/` 目录生成目录树、文件内容和搜索结果。

返回对象：

- `path`
- `name`
- `type`
- `children`
- `snippet`
- `score`

## 后续待补对象

- Attachment
- Reminder
- KnowledgeIndex
- Contact
- LearningPlan
- WorkProject

这些对象进入二期或独立模块深化时再建表，避免一期过早膨胀。
