# Matrix PRP App

这里是 Matrix PRP 的应用工程目录，用于承载 Web、移动端、CLI 和后端服务开发。

## 目录结构

```text
app/
  backend/    Spring Boot API 服务
  web/        Vue 3 + TypeScript Web 管理端
  mobile/     uni-app + Vue 3 + TypeScript 移动端
  cli/        Node.js + TypeScript 命令行工具
  docs/       产品、技术、接口、数据模型和问题记录文档
  docker/     本地开发基础设施配置
  scripts/    开发、验证、初始化和构建脚本
```

## 一期目标

一期先完成个人资源管理平台的基础闭环：

- 用户登录与 JWT 鉴权
- Dashboard 今日概览
- 通用记录系统
- 标签管理
- 任务与计划
- 财务基础记录与统计
- 复盘管理
- `knowledge/` Markdown 知识库浏览和搜索

## 开发原则

- 后端作为结构化数据和认证的唯一中心。
- Web 负责深度管理、表格、图表和复盘。
- Mobile 负责快速记录、提醒和轻量查看。
- CLI 负责快速录入、查询和自动化操作。
- `knowledge/` 继续作为长期 Markdown 知识资产。

## 本地启动

启动前可以先做一次环境体检：

```powershell
.\app\scripts\check-env.ps1
```

### 1. 启动 MySQL

```powershell
.\app\scripts\start-infra.ps1
```

### 2. 启动后端

```powershell
.\app\scripts\start-backend.ps1
```

后端启动后可以回到仓库根目录做一次 API 冒烟检查：

```powershell
.\app\scripts\smoke-api.ps1
```

如果 8080 端口被旧后端占用，脚本会显示占用进程。确认是旧 Matrix PRP 后端后，可以使用：

```powershell
.\app\scripts\start-backend.ps1 -StopExisting
```

后端默认地址：

- API: `http://localhost:8080`
- Health: `http://localhost:8080/api/health`
- OpenAPI JSON: `http://localhost:8080/v3/api-docs`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- CORS: 开发期允许 `http://localhost:*` 和 `http://127.0.0.1:*` 访问 `/api/**`

### 3. 启动 Web

```powershell
cd app/web
npm install
npm run dev
```

Web 默认地址：`http://localhost:5173`

Web 开发服务默认将 `/api` 代理到 `http://localhost:8080`。如需修改后端地址，可在 `app/web/.env` 中设置：

```text
VITE_API_PROXY_TARGET=http://localhost:8080
```

### 4. 启动移动端 H5

```powershell
cd app/mobile
npm install
npm run dev:h5
```

移动端 H5 同样支持通过 `app/mobile/.env` 的 `VITE_API_PROXY_TARGET` 修改后端代理目标。

### 5. 使用 CLI

```powershell
cd app/cli
npm install
npx tsx src/index.ts --help
npm run dev -- health
```

测试环境（仅 `test` Profile）存在 `admin / matrix-prp`。常规运行使用真实数据库用户，需配置安全环境变量，详见 `app/docs/technical/multi-user-foundation.md`。

## 本地验证

可以使用统一脚本验证一期工程骨架：

```powershell
.\app\scripts\verify.ps1
```

脚本会执行后端测试、Web 构建、移动端类型检查与 H5 构建、CLI 构建。若只想验证部分端，可以使用跳过参数：

```powershell
.\app\scripts\verify.ps1 -SkipMobile
```

## 数据库无损升级

旧数据库不可直接启用 Flyway 自动基线。执行升级前必须阅读 [P0 数据库迁移与回滚手册](docs/technical/safe-db-migrations-p0.md)。
