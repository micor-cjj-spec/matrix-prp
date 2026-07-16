# API Docs

这里管理 Matrix PRP 的接口设计、接口草案、接口变更和联调说明。

## 运行时文档

后端已接入 springdoc-openapi：

- OpenAPI JSON: `http://localhost:8080/v3/api-docs`
- Swagger UI: `http://localhost:8080/swagger-ui.html`

业务接口默认需要 JWT Bearer Token。先调用：

```http
POST /api/auth/login
```

开发账号：

- Username: `admin`
- Password: `matrix-prp`

拿到 `token` 后，在 Swagger UI 右上角 `Authorize` 中填写：

```text
Bearer <token>
```

## 文档索引

- `overview.md`: API 风格、统一响应、错误码和一期接口清单。
- `changes/`: 接口变更记录。

## 维护约定

- 新增或修改后端接口时，同步更新 `overview.md`。
- 影响调用方的变更记录到 `changes/`。
- 运行时 OpenAPI 作为接口联调入口，Markdown 文档作为设计和决策沉淀。
