# Scripts

这里存放本地开发、验证、初始化、构建、代码生成和数据导入脚本。

## verify.ps1

统一验证一期工程骨架，不依赖本地 MySQL 或 Docker Desktop。

默认会依次执行：

- Backend: `mvnw.cmd test`
- Web: `npm run build`
- Mobile: `npm run type-check` 和 `npm run build:h5`
- CLI: `npm run build`

运行：

```powershell
.\app\scripts\verify.ps1
```

可按需跳过某一端：

```powershell
.\app\scripts\verify.ps1 -SkipMobile
.\app\scripts\verify.ps1 -SkipBackend -SkipWeb
```

## check-env.ps1

检查本地开发环境是否具备启动一期工程的基础条件。

默认检查 Java、Node.js、npm、Git、Docker 客户端、关键配置文件和知识库目录。Docker Desktop 未启动时只给出警告，不会阻塞检查；如果需要把 Docker 作为强制条件，可以使用 `-StrictDocker`。

```powershell
.\app\scripts\check-env.ps1
.\app\scripts\check-env.ps1 -StrictDocker
```

## start-infra.ps1

启动本地基础设施并等待 MySQL 容器健康。

```powershell
.\app\scripts\start-infra.ps1
.\app\scripts\start-infra.ps1 -TimeoutSeconds 180
```

## start-backend.ps1

启动 Spring Boot 后端。脚本会先检查端口是否被占用，避免连接到旧的后端进程。

```powershell
.\app\scripts\start-backend.ps1
.\app\scripts\start-backend.ps1 -Port 18080
.\app\scripts\start-backend.ps1 -StopExisting
```

## smoke-api.ps1

检查正在运行的后端 API 是否可用。脚本会访问 health、登录、当前用户、Dashboard 和模块接口，覆盖公开接口、JWT 鉴权和基础业务读取。

```powershell
.\app\scripts\smoke-api.ps1
.\app\scripts\smoke-api.ps1 -ApiBaseUrl http://localhost:8080/api
```
