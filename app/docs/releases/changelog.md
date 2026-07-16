# Changelog

## Unreleased

### Added

- 新增 `app/` 应用工程目录，拆分 backend、web、mobile、cli、docs、docker、scripts。
- 搭建 Spring Boot 后端，提供认证、模块、Dashboard、记录、标签、任务、财务、复盘和知识库接口。
- 接入 JWT 鉴权、统一响应、统一错误处理和 springdoc-openapi。
- 新增 Vue 3 Web 管理端，覆盖登录、Dashboard、记录、标签、任务、财务、复盘和知识库页面。
- 新增 uni-app Mobile H5，覆盖登录、今日状态、快速记录和快速记账。
- 新增 Node.js CLI，覆盖登录、配置、Dashboard、模块、标签、记录、任务、财务、复盘和知识搜索命令。
- 新增 Docker Compose MySQL 初始化脚本。
- 新增统一验证脚本 `app/scripts/verify.ps1`。

### Changed

- 文档中心改为目录化管理，拆分产品、技术、API、数据、Bug、决策、发布和 AI notes。
- 一期产品设计、API 总览、技术架构、开发指南、测试指南和数据模型文档已整理为可读中文。
- Dashboard 增加逾期任务数和高优先级任务。
- 任务列表支持按优先级筛选。
- 标签、记录、任务、财务、复盘均补齐基础维护能力。

### Verification

- `.\app\scripts\verify.ps1` 当前可通过。
- 后端测试、Web 构建、Mobile 类型检查与 H5 构建、CLI 构建均纳入验证脚本。
