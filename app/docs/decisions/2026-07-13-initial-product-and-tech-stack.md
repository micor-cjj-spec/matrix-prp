# Initial Product And Tech Stack

## 背景

Matrix PRP 从原有 Markdown 知识库升级为多端个人资源管理平台。

项目需要继续保留 `knowledge/` 作为长期知识资产，同时新增应用工程，为 Web、Mobile、CLI 和后端服务提供统一基础。

## 决策

- 后端采用 Spring Boot 3。
- 数据库采用 MySQL。
- ORM 采用 MyBatis Plus。
- 认证采用 Spring Security + JWT。
- 本地基础设施采用 Docker Compose。
- 接口文档采用 springdoc-openapi。
- Web 采用 Vue 3 + TypeScript + Vite + Element Plus。
- Mobile 采用 uni-app + Vue 3 + TypeScript。
- CLI 采用 Node.js + TypeScript + Commander。

## 产品形态

Matrix PRP 定位为 Web + Mobile + CLI 的个人资源管理平台。

一期优先完成基础闭环，不一次性做满所有模块：

- Dashboard
- Records
- Tags
- Tasks
- Finance
- Reviews
- Knowledge

## 影响

- 后端成为结构化数据和认证的中心。
- Web 承担深度管理和分析。
- Mobile 承担快速记录和今日查看。
- CLI 承担自动化和开发者式快速录入。
- `knowledge/` 暂不迁移，先做只读浏览和搜索。

## 后续观察点

- 是否需要 Flyway 或 Liquibase 管理长期数据库迁移。
- 是否需要 Redis 支撑提醒、缓存或异步任务。
- 是否需要基于 OpenAPI 生成 Web、Mobile、CLI 共用 SDK。
- 是否引入 AI 做分类、摘要、复盘和知识检索增强。
