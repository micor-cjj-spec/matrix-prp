# Architecture

## 总体架构

```text
Web + Mobile + CLI
        |
        v
Spring Boot REST API
        |
        v
MySQL + knowledge Markdown
```

## 技术栈

### Backend

- Spring Boot 3
- Java 21
- Spring Web
- Spring Validation
- Spring Security + JWT
- MyBatis Plus
- MySQL
- AutoTable
- springdoc-openapi

### Web

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- Element Plus
- Axios
- ECharts

### Mobile

- uni-app
- Vue 3
- TypeScript

### CLI

- Node.js
- TypeScript
- Commander
- Axios

### Infrastructure

- Docker Compose
- MySQL
- 后续可按需加入 Redis

## 工程目录

```text
app/
  backend/
  web/
  mobile/
  cli/
  docs/
  docker/
  scripts/
```

## 架构原则

- 后端作为结构化数据和认证中心。
- Web、Mobile、CLI 共用同一套 REST API。
- 已建立邀请制注册、JWT 与按用户归属的数据隔离；跨用户访问必须经过后端校验，不能仅依赖前端菜单。
- 业务功能登记与 Web 菜单元数据统一维护在 `app/config/feature-registry.json`，参见 `feature-registry.md`。
- 通用能力优先：记录、标签、任务、复盘、附件、提醒。
- 知识库为服务器共享 Markdown 目录，当前仅管理员可访问；未来个人知识库必须独立考虑隔离。
- 业务模块保持模块化单体，不因功能增长直接拆成微服务。
