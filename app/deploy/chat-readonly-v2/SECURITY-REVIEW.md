# PRP ChatGPT 固定只读运维 V2：安全复核与上线阻断清单

> 审查范围：Issue #309、设计 PR #310、离线实现 Draft PR #358。本文仅为审查记录，**不是上线或权限授权**。
>
> 当前结论：**OFFLINE-PASS（上一精确提交） / HOST-PILOT-NO-GO / PRODUCTION-NO-GO**。
> 历史证据：PR #358 HEAD `d6377fff6c20e447210f129f5d775666a360fec7`：离线 46/46 通过（Actions #45034552573）、完整 CI 尝试 2 为 30/30 通过（Actions #45034552579）。**后续提交需分别核验，不能沿用旧绿灯。**

## 1. 明确三个不同的信任域

| 层级 | 可信边界及最低校验 | 当前实现与缺口 |
| --- | --- | --- |
| ChatGPT 用户意图 | 在同一对话中逐条展示固定查询和数据范围，得到明确批准 | ChatGPT 的对话批准**不是 GitHub 可验证的数字签名**。GitHub owner 账号认证不能证明对话意图；不能宣称服务端有独立聊天批准证明 |
| GitHub Issue 触发 | 真实 Actions `issue_comment.created` 上下文、固定仓库 ID/owner ID/固定 V2 Issue、禁止 PR 评论与编辑/跨路由 | `parse_event_fixture` 仅验证调用者提供的**合成上下文**，当前没有已审查的生产级 Actions 入口或已固定的真实 V2 Issue；不能信任请求体提供的 `trusted_runtime` |
| 主机端只读权限 | 完全独立于 V1 的低权限进程/强制命令/独立证书；不能访问 sudo、Docker socket、DB 或敏感日志 | 仅有纯函数与合成数据；未创建账户/SSH/密钥/网关，未访问真实主机 |

## 2. 已完成的离线证据（仅限具体提交）

- 固定零参数操作 `host_root_fs_usage` 和 `prp_app_health`；GitHub CI 查询仍直接使用连接器，不走 SSH。
- JSON 采用 exact-schema 和禁止重复键规则；拒绝未知命令、路径、URL、SQL、异常 UUID/nonce/TTL。
- 模拟根盘指标通过 `statvfs('/')` 固定路径投影；健康检查只映射最小 liveness/readiness 字段，**不**返回 `/api/health/runtime` 的原始 JSON、路径、profiles 或数据库诊断。
- SQLite 离线原型采用原子 `BEGIN IMMEDIATE` 与双重唯一索引；测试覆盖进程重新打开、并发重复、宽松文件权限、符号链接、硬链接及删除后意外重建。
- 临时自签测试证书可完成 CMS AES-256-GCM 加密/解密回环，篡改及错误收件人被拒绝；**CMS 收件人加密和认证解密不等于调用者身份认证**。
- 已针对 `ApiResponse` 响应包装识别出额外校验要求：仅当 HTTP 200、`code=SUCCESS`、`data.status=UP`、`data.service=matrix-prp-backend` 时映射 liveness `reachable`；相关实现需以最新提交 CI 验收为准。

## 3. 阻断项和可证伪的验收条件

### G1：真实 GitHub 事件来源、路由和凭据隔离 — 未完成

- 设计唯一 V2 Issue（不得与 V1 Issue #277 共用）；固定数值且将值写入静态工作流和服务端核验，拒绝评论编辑、其他仓库/Issue、PR 评论、fork 触发。
- 事件来源使用不可由用户评论伪造的 GitHub Actions runtime context；`github.actor` 与事件 sender/comment author 的严格一致性由受保护 workflow 确保。不能依赖从 Issue 正文解析出的所谓 `trusted_runtime`。
- 工作流中的处理逻辑只允许明确批准的加密**固定只读**调用，不得动态解释 GitHub 评论为 Bash。
- 不得把 owner 身份校验表述为“证明了 ChatGPT 对话批准”。在当前可用能力下，聊天批准由对话侧流程确保，服务端无法独立强验证；此风险须显式接受或保持主机通道关闭。

### G2：加密身份、密钥与完整结果绑定 — 未完成

- 独立的 V2 服务端密钥/证书与 V1 完全隔离；生成、保管、轮换、吊销、过期、私钥文件模式需专门审查，绝不可把真实私钥提交到 GitHub。
- 必须实际解析并验证 X.509 公钥格式、有效期、允许算法和指纹固定策略；当前 `answerCertificate` 的 PEM 字符串形状检查不是 X.509 验证。
- 请求和结果加密均绑定 `jobId`、`operation`、`nonce`、固定响应通道/评论 ID、签发时间与失效时间；不应仅依赖某个公开评论能被解密就假定其来自授权服务端。
- 真实端到端试点需证明不可在 GitHub 输出、Runner stdout、Actions artifact、PR 评论或应用日志获得秘钥或明文敏感输出。

### G3：防重放、DoS 与文件系统一致性 — 未完成

- 离线 SQLite 方案尚需解决相同 OS 用户竞争、目录祖先路径及文件替换竞态、数据库损坏、磁盘耗尽、文件描述符耗尽、journal/WAL 权限及异常恢复。
- 当前原型保留所有旧 nonce/jobId，尚无已证明安全的保留期、总条数上限、清理/撤销策略；不能直接变成长驻主机服务。
- 限制单次请求大小/CPU/超时、最大并发与单位时间调用次数；对不确定是否已执行的请求不得自动重试，必须可查询单次响应状态。
- 测试后需要在独立受控环境做故障注入，并以失败默认拒绝作为条件。

### G4：生产运行隔离与运维撤销 — 未完成

- 独立非 root 用户、独立 SSH 身份与强制命令，只允许固定 `statvfs('/')` 或经过审核的本地健康探针；不允许动态 URL、路径、PID、容器/日志/SQL。
- 主机端密钥、known_hosts 固定校验、源地址和超时、防 SSH forward/SFTP/PTY、权限审计与吊销演练均需真实证据。
- 不能复用 V1 的执行器、root-only 开关、GitHub `PRP_CHAT_SHELL_ENABLED` 或生产密钥；真实服务器试点需要**新的、独立的明确批准**。
- 生产业务发布锁 `app/deploy/publication-hold.json`、主分支保护和数据恢复要求保持不变。

### G5：健康探测语义 — 未完成真实核验

- `GET /api/health` 仅证明服务的 HTTP 存活性，不代表数据库、知识库或业务可用。只在可信固定来源成功且响应 schema 匹配时输出 `reachable`；HTTP 4xx（含 401/403/404/429）属于授权、路由或限流等含混情形，**只返回 `unknown`，不能据此宣称服务器不可达**；HTTP 5xx 可映射 `unreachable`，但**不等于 TCP/网络不可达**。不输出原始状态码或响应正文。
- `GET /api/health/runtime` 可包含内部 `knowledgeRoot`、`activeProfiles` 等诊断内容；V2 不得返回原始 JSON，默认禁用这个来源。
- 禁止把健康 API 里的硬编码 `version=0.1.0` 当成已部署的真实版本标识。只有经过验证的版本来源才能独立立项新增。

## 4. 独立复核结论与下一步

| 项目 | 决策 |
| --- | --- |
| 继续离线代码审查、负例补齐、保留 Draft PR | **允许** |
| 使用现有 GitHub 连接器读取 CI 信息 | **允许，无需主机连接** |
| 宣称可从 ChatGPT 常态读取 PRP 服务器 | **不允许，尚无真实端到端证据** |
| 创建 V2 主机账号/密钥/SSH 或调用生产主机 | **NO-GO，需用户单独明确授权及审查** |
| 重开 V1 通用 Shell、自动合并 main、生产发布或去掉发布锁 | **NO-GO** |

验收门槛不是“离线单测全部绿”本身；必须有**真实事件来源证据、最小权限认证证据、可撤销证明、恶意/重放拒绝、真实加密结果绑定和用户独立批准**。如缺任何核心安全边界，停留在直接 GitHub 只读与离线 Draft 阶段。
