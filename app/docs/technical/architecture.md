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
- 表设计预留 `user_id`，一期按单用户使用。
- 通用能力优先：记录、标签、任务、复盘、附件、提醒。
- 知识库先只读集成，再逐步做搜索、编辑和 AI 能力。
