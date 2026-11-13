# PRP Personal OS V0.5 — T-001 数据与本体契约（审查候选）

> Requirement: [#181](https://github.com/micor-cjj-spec/matrix-prp/issues/181) · T-001: [#182](https://github.com/micor-cjj-spec/matrix-prp/issues/182)
>
> **状态：CONTRACT REVIEW ONLY。** 本文件不是生产迁移指令，也不是外部模型读取私人数据的授权。

## 1. MVP 约束

- 目标：以职业发展为试点，走通 `事实 -> 目标 -> 任务 -> AI 建议 -> 用户确认 -> 复盘`。
- 后端保持 Java 21 / Spring Boot / MySQL 的模块化单体。原业务表继续是权威来源；语义声明仅引用已有数据。
- 本期最多**两张新增表**：`prp_goals` 和 `prp_personal_assertions`。不引入图数据库、独立索引服务或新 Agent 进程。
- 本体词汇受 Java `PersonalOntology` 白名单约束；它只检查语义类型，不替代数据库实体的用户归属校验。
- 公开 GitHub 仅放契约、代码和合成示例，**禁止写入真实人生经历、私人对话、身体/财务数据及密钥**。

## 2. 语义词汇 V0

节点类型：`PERSON`、`GOAL`、`SKILL`、`EVENT`、`RESOURCE`、`TASK`、`RECORD`、`REVIEW`、`LITERAL`。

| 谓词 | Subject | Object | 含义 |
|---|---|---|---|
| PURSUES | PERSON | GOAL | 追求目标 |
| HAS_SKILL | PERSON | SKILL | 具备技能 |
| REQUIRES | GOAL | SKILL | 目标需要技能 |
| DEMONSTRATES | EVENT | SKILL | 经历证明技能 |
| ADVANCES | TASK | GOAL | 任务推进目标 |
| EVALUATES | REVIEW | GOAL | 复盘评价目标 |
| DOCUMENTS | RECORD | EVENT | 记录描述事件 |
| SUPPORTS | RESOURCE | GOAL | 资源支持目标 |
| CONSTRAINS | RESOURCE | TASK | 资源约束行动 |
| PREFERS | PERSON | LITERAL | 经确认的偏好 |
| HAS_BACKGROUND | PERSON | LITERAL | 经确认的背景陈述 |

这不是自由知识图谱 API。未知谓词、类型错误、未核实的实体键、跨用户引用必须拒绝。

## 3. 目标表：prp_goals（拟议契约）

| 字段 | 建议类型 | 说明 |
|---|---|---|
| id | BIGINT PK | 自增标识 |
| user_id | BIGINT NOT NULL | 必须属于已认证用户，FK -> prp_users |
| title | VARCHAR(255) NOT NULL | 目标名称 |
| description | TEXT | 目标原因与范围 |
| domain | VARCHAR(64) NOT NULL | 例如 career / learning |
| status | VARCHAR(16) NOT NULL | PLANNED / ACTIVE / PAUSED / COMPLETED / CANCELLED |
| priority | VARCHAR(16) NOT NULL | low / medium / high，由用户设定 |
| success_criteria | TEXT | 成功标准，允许尚未定义 |
| target_date | DATE NULL | 不能由模型自行编造 |
| request_key | VARCHAR(80) NULL | 创建请求的幂等键，按 user_id 唯一 |
| created_at / updated_at | DATETIME(6) NOT NULL | 服务器时间 |
| deleted | TINYINT NOT NULL | 业务软删除标记 |

建议索引：`(user_id,status,deleted,target_date)`、唯一 `(user_id,request_key)`（NULL 允许多行）。
不要求首次版本自动计算目标达成率，也不自动修改现有 Task 表。

## 4. 声明表：prp_personal_assertions（拟议契约）

| 字段 | 建议类型 | 说明 |
|---|---|---|
| id, user_id | BIGINT | 主键 + 所属用户，必须由服务端身份确定 |
| subject_type / subject_ref | VARCHAR(32) / VARCHAR(128) | 受控类型与实体键；主体不得为 LITERAL |
| predicate | VARCHAR(64) | 仅允许 PersonalOntology 中定义的关系 |
| object_type / object_ref | VARCHAR(32) / VARCHAR(128) NULL | 实体关系使用 object_ref |
| object_value | TEXT NULL | 仅 LITERAL 使用，禁止存密钥/Token |
| source_type / source_ref | VARCHAR(32) / VARCHAR(128) NULL | 对话、用户输入、任务、记录等证据指针 |
| origin | VARCHAR(24) | USER_CONFIRMED / AI_CANDIDATE / BUSINESS_REFERENCE（来源属性，不代表事实状态） |
| status | VARCHAR(16) | PENDING / CONFIRMED / SUPERSEDED / INVALID |
| sensitivity | VARCHAR(16) | NORMAL / SENSITIVE / RESTRICTED |
| valid_from / valid_to | DATE NULL | 事实有效期，与写入时间不同 |
| supersedes_id | BIGINT NULL | 新事实替代旧事实的标识，必须校验同一用户 |
| request_key | VARCHAR(80) NULL | 按 user_id 唯一的请求幂等键 |
| created_at / updated_at | DATETIME(6) | 创建 / 修改时间 |

校验：`object_type=LITERAL` 时只允许非空 `object_value`；实体对象必须有 `object_ref`，不能同时携带文本值。两种形式互斥。时间范围不得倒置。建议索引：`(user_id,subject_type,subject_ref,status)`、`(user_id,object_type,object_ref,status)`、`(user_id,request_key)` 唯一。

关系端点必须按 `user_id` 验证实体确实属于当前用户。TASK/RECORD/REVIEW/GOAL 从现有 Service/Repository 解析；SKILL/EVENT/RESOURCE 若尚无可验证的受控标识来源，则拒绝持久化，不可使用任意字符串绕过验证。

## 5. 事实与隐私语义

- `PENDING`、`SUPERSEDED`、`INVALID` 默认不得作为“当前已确认事实”出现在 AI 上下文。
- `AI_CANDIDATE` 可以在用户确认后变为 `CONFIRMED`，但来源类型保持原样，不改写成用户亲自提供的证据。
- 事实被替代不等于失真；删除与历史失效是独立操作。永久删除必须清理相应可控派生索引/缓存；历史审计不能无期限保留敏感正文。
- 不将私人事实写入公开 Markdown 仓库；删除原始业务记录或撤销证据访问权限后，不得继续作为可展示的证据。
- PRP 本地查询许可、向第三方模型发送上下文许可、修改业务数据许可分别鉴权。不得将 `prp.tasks.read` 视为 `prp.memory.read`。
- 任何 SQL、用户 ID、任意 URL 或关联实体键均不得由模型越过服务端的白名单及授权检查。

## 6. API 与职责边界

- T-002：`GET /api/memory`、候选生成、确认、更正、删除；Service 执行用户归属、来源和生命周期校验。
- T-003：`GET/POST/PATCH /api/goals`，目标上下文查询；不复制或修改现有任务。
- T-004：前端确认卡片、目标界面和基于 Record 的事件时间轴。
- T-005：仅对已授权、有效的声明建立 bounded context，不因关系存在而泄露被引用业务记录。
- T-006：新增 MCP Scope 与受控工具契约需经过 OAuth 白名单和独立安全评审；写入沿用草稿审批，不直接调用修改 API。

## 7. V30 迁移阻塞项（不能绕过）

当前 main 到 V29，`app/deploy/migration-policy.json` 存储受哈希校验的 `create-empty` 迁移清单；
`app/scripts/verify-db-migrations.mjs` 校验实际迁移文件集；
`FlywayV28ToV29IT`、`IsolatedV28BackupRestoreMcpV29IT` 和部分 OCI 工具存在 V29 固定范围假设。

**本 Draft PR 只提交可编译语义词汇、测试和审查契约；不创建可执行的 V30 迁移文件。**

正式增加 V30 时必须在独立审查下：
1. 重新确认最新 main 和所有开放 PR 的迁移版本；审查 CREATE-EMPTY 合法性。
2. 创建 V30（仅新建两张空表），计算确切 SHA-256 并登记 policy；不得修改 V1–V29。
3. 将历史 V28→V29 专项测试明确限定到目标 V29，而不是关闭测试或放宽安全断言。
4. 评审 OCI/发布验证工具的版本约束，确保新 V30 校验可用且不削弱 V29 遗留安全验收。
5. 在隔离 MySQL 上跑 Flyway fresh / V29→V30 / schema validate / rollback-readiness 和跨用户测试。
6. CI 和安全审查通过后，仍不得据此直接迁移生产。

## 8. T-001 完成门槛

本阶段的词汇代码可以独立合并评审，但 **T-001 不得标记 DONE**，直到 V30 迁移、实体/所有权校验实现和自动化安全测试全部通过。禁止将 PR 创建或 Java 编译通过视为 T-001 完成。
