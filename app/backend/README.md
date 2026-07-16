# Backend

Spring Boot API 服务目录。

默认技术栈：

- Spring Boot 3
- Java 17 或 Java 21
- Spring Web
- Spring Validation
- Spring Security + JWT
- MyBatis Plus
- MySQL
- AutoTable
- OpenAPI / Knife4j

一期优先建设：

- 用户与认证
- 通用模块、记录、标签、任务、复盘
- 财务基础接口
- 知识库读取与索引接口

## 本地启动

先启动 MySQL：

```powershell
..\scripts\start-infra.ps1
```

再启动后端：

```powershell
..\scripts\start-backend.ps1
```

## 验证

```powershell
.\mvnw.cmd test
```

启动后访问：

- `http://localhost:8080/api/health`
- `http://localhost:8080/swagger-ui.html`

## 本地跨域

开发期后端允许 `http://localhost:*` 和 `http://127.0.0.1:*` 访问 `/api/**`，并支持 `Authorization` 请求头，方便 Web、移动端 H5 和临时预览端口连接本地 API。

## 开发账号

- Username: `admin`
- Password: `matrix-prp`
