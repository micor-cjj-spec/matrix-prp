# Docker

本地开发基础设施配置目录。

一期优先放置：

- MySQL Docker Compose 配置
- 数据库初始化脚本
- 后续可扩展 Redis、对象存储或搜索服务

## 启动

```powershell
docker compose up -d
```

也可以在仓库根目录使用脚本启动并等待 MySQL 健康：

```powershell
.\app\scripts\start-infra.ps1
```

## 停止

```powershell
docker compose down
```

## 数据库连接

- Host: `localhost`
- Port: `3306`
- Database: `matrix_prp`
- Username: `matrix_prp`
- Password: `matrix_prp`

## 健康检查

MySQL 容器内置 healthcheck，使用 `mysqladmin ping` 确认数据库可以接受连接。查看状态：

```powershell
docker inspect -f "{{.State.Health.Status}}" matrix-prp-mysql
```
