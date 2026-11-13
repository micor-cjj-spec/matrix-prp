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

## 7. V30 增量迁移与保护门槛

Draft PR #190 已在**未合并的独立分支**增补 `V30__personal_os_goals_and_assertions.sql`。迁移仅创建两张空表，没有数据回填、触发器、ALTER 或生产执行路径。
- SQL SHA-256（LF/UTF-8）：`e9da502ffef9bd8cf3fa4e6256658de078a610a5694270f1b9124238e00fab0b`
- 对应 `app/deploy/migration-policy.json` 的 `create-empty` 规则，显式声明两张表。
- 原 V1–V29 文件和哈希保持不变；旧的 V28→V29 合成测试固定 `target=29`，不会误执行 V30。
- OCI 检验升级为严格验证 V1–V30 的完整连续版本集合及二进制字节一致性；不放宽额外文件/修改字节/重复 ZIP 条目的拒绝逻辑。
- 历史生产元数据审查工具仍只认可 V24/V28/V29 的既定历史终态，**没有**将 V30 自动提升为历史生产验收许可。
- CI Flyway 测试使用一次性合成用户、事务回滚，检查 V30 新表、所有者 FK、请求幂等键以及跨用户 `supersedes_id` 的复合外键拒绝。该测试不能替代真实恢复演练。

需要独立完成的门禁：
1. 检查所有实际开放 PR 和生产服务器状态是否有 V30 版本冲突；PR 创建时的 main 锚点为 `2b8ca609`。
2. 运行 GitHub 全量 CI，包括迁移政策/控制器兼容性、V28→V29 历史验证、V30 CI MySQL、Docker OCI 验证。
3. 补充单独的隔离 V29→V30 populated-data 证据，特别验证旧表主键/字段/行指纹保持不变。
4. 实现业务层端点实体解析、当前用户所有权与 `LITERAL` 数据审查；数据库 FK 只保证 owner 和 supersedes 的部分约束，**不**自动保证 polymorphic object 引用的归属。
5. 发布前需要独立授权的备份/恢复演练和生产检查。此 Draft PR 不构成 main 合并、发布或生产迁移批准。

## 8. 未落实实体的处理策略（轻量 MVP）

T-001 的本体词汇列出了 SKILL、EVENT、RESOURCE，但它们目前**没有稳定、可独立校验的实体表/受控命名空间**。本期不把任意字符串或 AI 生成的键视为持久实体，也不根据一份普通记录就认定用户具备某个技能：

- PERSON / GOAL / TASK / RECORD / REVIEW：可以通过当前登录用户和具体持久数据归属校验。
- LITERAL：是附着在已验证主体上的受限值，没有独立的 `object_ref`，最多 512 个 Java UTF-16 字符；其状态仍需要用户确认。
- SKILL / EVENT / RESOURCE：仅保留为**未来可扩展词汇**，当前实体引用必须拒绝。后续优先基于可验证的用户确认记录或明确归属的资源实体建立解析策略，再考虑扩展关系；不预先添加三张业务表或无约束的名称节点。

`PersonalOntologyAssertionGuard` 是业务写入前的额外校验组件：核对谓词和两端类型、实体归属、证据来源（USER_INPUT/RECORD/TASK/REVIEW）、LITERAL 与实体互斥、有效时间区间。它不负责用户确认流程，也不替代源记录撤销同步、敏感数据筛选或向模型传输授权。这些必须由 T-002/T-005 的 Service 处理。

**迁移并发冲突：** Draft PR #180 和 #190 均有不同的 V30。当前 main 仍为 V29，虽各自 CI 能通过，**不允许顺序直接合并**。暂定 #180 先使用 V30，Personal OS 待其 SQL/Policy 定稿并进入共同集成基线后顺延到 V31，并重新做 SHA-256、历史迁移和 OCI 校验。用户未批准 main/生产变更。

## 9. T-001 完成门槛



在完整实体解析、所有权校验、V30 隔离 MySQL 升级回归及上述安全检查通过前，T-001 继续标记为 **IN PROGRESS**。不得把 Draft PR、编译或 CI 单项通过等同于功能和生产验收完成。
