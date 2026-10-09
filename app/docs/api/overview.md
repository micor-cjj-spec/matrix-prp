# API Overview

## 风格约定

- 使用 REST API。
- 请求和响应使用 JSON。
- 业务接口默认需要 JWT Bearer Token。
- 响应体使用统一结构。
- 运行时接口文档由 springdoc-openapi 生成。

## 基础路径

```text
/api/auth
/api/health
/api/users
/api/modules
/api/dashboard
/api/records
/api/tags
/api/tasks
/api/finance
/api/reviews
/api/knowledge
```

## 运行时文档

- OpenAPI JSON: `http://localhost:8080/v3/api-docs`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- Health: `http://localhost:8080/api/health`
- Runtime health: `http://localhost:8080/api/health/runtime`

开发账号：

```text
username: admin
password: matrix-prp
```

## 统一响应

成功响应：

```json
{
  "code": "SUCCESS",
  "message": "OK",
  "data": {}
}
```

错误响应：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "title must not be blank",
  "data": null
}
```

当前错误类型：

- `400 VALIDATION_ERROR`: 参数校验失败、缺少参数、非法参数。
- `401 UNAUTHORIZED`: 未登录或 JWT 无效。
- `404 NOT_FOUND`: 资源不存在。
- `500 INTERNAL_ERROR`: 未预期服务端错误。

## 一期接口清单

### Health

- `GET /api/health`: 基础服务状态、版本号和 API 契约标识。
- `GET /api/health/runtime`: 本地运行时诊断，返回 `persistence`、`database`、`knowledgeRoot`、`knowledgeAvailable` 和 `activeProfiles`。

### Auth & User

- `POST /api/auth/login`
- `GET /api/users/me`

### Modules & Dashboard

- `GET /api/modules`
- `GET /api/modules/features`
- `GET /api/modules/domains`
- `GET /api/dashboard/summary`: 返回今日、逾期、待安排任务列表及数量、高优先级任务、最近记录和财务摘要。今日/逾期/待安排使用同一个任务快照；高优先级列表最多展示 5 条。

### Records

- `GET /api/records`: 支持 `moduleCode`、`tagId`、`recordDate`、`keyword`。
- `POST /api/records`: 创建记录，支持 `tagIds`。
- `PUT /api/records/{id}`: 更新记录，支持替换 `tagIds`。
- `DELETE /api/records/{id}`: 删除记录。

### Tags

- `GET /api/tags`: 查询标签列表。
- `POST /api/tags`: 创建标签。
- `PUT /api/tags/{id}`: 更新标签。
- `DELETE /api/tags/{id}`: 删除标签。

### Tasks

- `GET /api/tasks`: 支持 `status`、`moduleCode`、`dueDate`、`priority`。
- `GET /api/tasks/summary`: 返回未完成、今日、待安排（新增 `unscheduledCount`）、逾期、未来 7 天、高优先级和状态分布概览。
- `POST /api/tasks`: 创建任务，`priority` 允许 `low`、`medium`、`high`。
- `PUT /api/tasks/{id}`: 更新任务基础信息，`priority` 允许 `low`、`medium`、`high`。
- `PATCH /api/tasks/{id}/status`: 更新任务状态，`status` 允许 `todo`、`in_progress`、`done`、`canceled`。
- `DELETE /api/tasks/{id}`: 删除任务。

任务分类规则：仅 `todo`/`in_progress` 视为未完成；今日 = 截止日期为今天；逾期 = 截止日期早于今天；待安排 = 无截止日期；未来 7 天 = 明天至第 7 天（含）。

### Finance

- `GET /api/finance/transactions`: 支持 `month`、`type`、`category`。
- `POST /api/finance/transactions`: 创建财务流水，`type` 允许 `income`、`expense`。
- `PUT /api/finance/transactions/{id}`: 更新财务流水，`type` 允许 `income`、`expense`。
- `DELETE /api/finance/transactions/{id}`: 删除财务流水。
- `GET /api/finance/summary/monthly`: 支持 `month=yyyy-MM` 查询指定月份。
- `GET /api/finance/summary/monthly/categories`: 按支出分类汇总指定月份金额和占比。
- `GET /api/finance/summary/monthly/accounts`: 按账户汇总指定月份收入、支出和结余。

- `GET /api/finance/accounts`: 查询财务账户列表。
- `POST /api/finance/accounts`: 创建财务账户。
- `PUT /api/finance/accounts/{id}`: 更新财务账户。
- `DELETE /api/finance/accounts/{id}`: 删除财务账户。
- `GET /api/finance/categories`: 查询财务分类列表，支持 `type=income|expense`。
- `POST /api/finance/categories`: 创建财务分类，`type` 允许 `income`、`expense`。
- `PUT /api/finance/categories/{id}`: 更新财务分类，`type` 允许 `income`、`expense`。
- `DELETE /api/finance/categories/{id}`: 删除财务分类。
### Reviews

- `GET /api/reviews`: 支持 `reviewType`、`moduleCode`、`periodStart`、`periodEnd`。
- `POST /api/reviews`: 创建复盘，`reviewType` 允许 `weekly`、`monthly`、`module`，`periodStart` 不能晚于 `periodEnd`。
- `PUT /api/reviews/{id}`: 更新复盘，`reviewType` 允许 `weekly`、`monthly`、`module`，`periodStart` 不能晚于 `periodEnd`。
- `DELETE /api/reviews/{id}`

### Knowledge

- `GET /api/knowledge/tree`
- `GET /api/knowledge/stats`
- `GET /api/knowledge/files?path=...`
- `GET /api/knowledge/search?q=keyword`
