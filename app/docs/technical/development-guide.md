# Development Guide

## 本地开发目标

一期本地开发需要能完成这条链路：

1. 使用 Docker Compose 启动 MySQL。
2. 启动 Spring Boot 后端。
3. 启动 Vue Web 前端。
4. 通过 Web、Mobile H5 或 CLI 调用后端 API。

## 启动命令

### MySQL

```powershell
.\app\scripts\start-infra.ps1
```

首次创建 MySQL 数据卷时会自动执行 `app/docker/mysql/init/001-schema.sql`。

### Backend

```powershell
.\app\scripts\start-backend.ps1
```

后端默认地址：

```text
http://localhost:8080
```

运行时 API 文档：

- `http://localhost:8080/v3/api-docs`
- `http://localhost:8080/swagger-ui.html`

后端启动后可以在仓库根目录运行 API 冒烟检查：

```powershell
.\app\scripts\smoke-api.ps1
```

如果需要确认当前后端是否连接了 MySQL 和 `knowledge/`，可以查看运行时诊断：

```powershell
Invoke-RestMethod http://localhost:8080/api/health/runtime
```

正常本地开发环境应返回 `persistence=mysql`、`database=UP`、`knowledgeAvailable=true`。

### Web

```powershell
cd app\web
npm install
npm run dev
```

Web 默认地址：

```text
http://localhost:5173
```

### Mobile H5

```powershell
cd app\mobile
npm install
npm run dev:h5
```

### CLI

```powershell
cd app\cli
npm install
npx tsx src/index.ts --help
```

登录开发后端：

```powershell
cd app\cli
npx tsx src/index.ts login -u admin -p matrix-prp
```

检查后端基础状态和运行时依赖：

```powershell
cd app\cli
npm run dev -- health
```

查看任务概览：

```powershell
cd app\cli
npm run dev -- task summary
```

查看账户维度财务汇总：

```powershell
cd app\cli
npm run dev -- finance accounts
```

搜索并读取知识库 Markdown：

```powershell
cd app\cli
npm run dev -- knowledge tree
npm run dev -- knowledge stats
npm run dev -- knowledge search Matrix
npm run dev -- knowledge read README.md
```

## 验证命令

推荐在仓库根目录运行统一验证脚本：

```powershell
.\app\scripts\verify.ps1
```

按端单独验证：

Backend:

```powershell
cd app\backend
$env:MAVEN_OPTS='-Xmx192m -XX:MaxMetaspaceSize=160m'
.\mvnw.cmd test
```

`app/scripts/start-backend.ps1` 会同时限制 Maven 和 Spring Boot 应用 JVM 的内存占用，适合当前本地开发机页面文件较紧的情况。

Web:

```powershell
cd app\web
npm run build
```

Mobile:

```powershell
cd app\mobile
npm run type-check
npm run build:h5
```

CLI:

```powershell
cd app\cli
npm run build
```

## 开发账号

一期开发阶段使用固定账号登录：

- Username: `admin`
- Password: `matrix-prp`

后续接入用户表后，再替换为数据库用户和密码加密校验。

## 代码组织

- 后端代码：`app/backend/`
- Web 代码：`app/web/`
- Mobile 代码：`app/mobile/`
- CLI 代码：`app/cli/`
- 工程脚本：`app/scripts/`
- Docker 配置：`app/docker/`

## 开发约定

- 新增后端接口时，同步更新 API 文档。
- 新增核心表或字段时，同步更新数据模型文档。
- 重要技术取舍写入 `decisions/`。
- 修复 Bug 时补充 `bugs/` 记录。
- 阶段完成后更新 `releases/changelog.md`。
