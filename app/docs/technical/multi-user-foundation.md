# Matrix PRP P0：多用户与数据隔离

当前阶段：功能分支验证中，**不能直接部署生产公网**。

## 功能

- `prp_users` 存储真实用户，用户名唯一，密码使用 BCrypt 哈希；`prp_invitations` 仅保存邀请码 SHA-256 哈希。管理员发放 7 天有效、只能使用一次的邀请。
- `POST /api/auth/login`：密码验证、签发 JWT；`POST /api/auth/register`：凭邀请码创建账户；`POST /api/auth/invitations`：仅管理员可发邀请码；`GET /api/users/me`：当前用户。
- JWT 按用户 ID 和用户名匹配实时数据库身份，禁用用户将失效。
- 任务、记录、财务交易、财务账户/分类、标签、复盘的数据查询、修改和删除均受当前用户隔离；关联记录的标签也需要归属验证。
- 服务器 `knowledge/` 是原始共享目录，`/api/knowledge/**` 暂仅管理员可读取。未来单独设计个人知识库，**不可将共享目录默认开放给注册用户**。
- 内存版存储只用于 `test` Profile；仅测试有固定 `admin / matrix-prp` 账号，不可将 `test` Profile 上生产环境。

## 已有 MySQL 库迁移步骤

1. 先**备份数据库并验证能够恢复**，暂停应用写入。
2. 在已有 MySQL 数据卷上手动执行 `app/docker/mysql/init/002-auth.sql`。注意 Docker MySQL 的 `docker-entrypoint-initdb.d` 仅在**空数据卷初始化**时执行。
3. 通过受保护的环境变量注入：`MATRIX_PRP_DB_URL`、`MATRIX_PRP_DB_USER`、`MATRIX_PRP_DB_PASSWORD`、`MATRIX_PRP_JWT_SECRET`（至少 32 字节高熵随机字符串）、`MATRIX_PRP_BOOTSTRAP_USERNAME`、`MATRIX_PRP_BOOTSTRAP_PASSWORD`（至少 12 位）。
4. 首次启动、用户表为空时创建管理员。历史单用户数据的 `user_id = 1` 默认归属于首个管理员：必须确认 `prp_users` 自增 ID 从 1 开始，避免错误归属。如果不是，请先确定数据库 ID 对应关系再执行迁移。
5. 先验证本机和真实 MySQL 的两账号隔离，再开放 HTTPS。

## 上线前剩余安全工作

- Nginx / 网关为登录、注册、邀请码接口添加 IP 与账号维度的限流；加上审计日志、TLS、最小权限数据库账号、备份恢复演练。
- 不允许从公网直接访问数据库的 3306 端口或后端的 8080 端口。
- 需要真实 MySQL 集成测试、手动回归和高并发邀请码消耗测试；MockMvc 的内存测试不是生产数据库测试。
- 后续新增密码找回、账号禁用管理、邀请码撤销、个人知识库，以及正式的迁移工具（如 Flyway）。
