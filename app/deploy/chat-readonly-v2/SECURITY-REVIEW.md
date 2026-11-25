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

## 5. 可信事件与对话授权的决策记录（ADR-V2-01，2026-11-22）

**状态：设计候选、未审批、未实现。** 本节仅细化 G1，不授权创建 GitHub 事件监听、生产密钥、主机账号或网络路径。

### 5.1 不可混淆的三种证明

1. **GitHub 平台事件**：受保护、固定版本的 Actions 工作流可以获取 GitHub 赋予的事件上下文。只有该工作流提供的 context 才可作为来源输入；Issue 评论、payload 中同名的“trusted_runtime”字段和外部用户提交的 JSON **都不能自证可信**。
2. **owner 账号授权**：核验 repository.id=1261866723、repository.full_name=micor-cjj-spec/matrix-prp、sender.id=comment.user.id=123868412、类型为 User，并绑定固定 V2 Issue、创建事件、评论 ID 与排除 PR 的条件。这只能证明 GitHub 账号在受保护的事件中发起请求，**不能证明发起者刚刚在 ChatGPT 对话里批准**。
3. **当前 ChatGPT 对话意图**：助手可在每项查询前展示白名单 operation、用途和读取字段并取得明确同意；当前设计尚无能让 GitHub 或主机**独立验证该同意**的签名凭据、OAuth 授权断言或平台签发证明。不得虚构这种证明，不能以笼统的“继续”替代单次真实主机操作批准。

### 5.2 三种可选路径（不自动作出上线选择）

| 路径 | 是否需服务器新权限 | 验证边界 | 当前结论 |
| --- | --- | --- | --- |
| A. ChatGPT 直接读取 GitHub CI | 否 | 已有 GitHub 连接器权限及仓库范围 | **继续优先采用**，无 SSH |
| B. 固定 V2 owner 评论 + 加密 + 独立低权限只读采集器 | 是 | GH 平台上下文 + owner 身份 + 固定操作，但**聊天批准无法独立密码学证明** | **需要用户单独评审、明确接受残余风险并批准有限试点后才可建设** |
| C. 每次请求附独立、可信用户持有密钥签名的授权断言 | 是 | 服务端独立验证签名、受众、有效期与操作范围 | 更强保证，但需要另行实现可验证签名来源及用户体验；**当前 ChatGPT/GitHub 工具链没有已验证的现成证明链**，不得宣称“聊天内点同意”会自动产生该断言 |

若安全准入要求“服务端必须独立证明 ChatGPT 当次批准”，且路径 C 尚不可用，则**禁止启用主机读取**；只能保留路径 A，不以 B 假装满足条件。路径 B 也绝不允许任意 Bash、数据库写入、生产发布或持久 root 权限。

### 5.3 未来可审查的固定 V2 事件适配器契约（**暂不实现**）

1. 在专门的 V2 Issue 上定义唯一精确路由，不能使用 V1 Issue #277、设计 Issue #309 或测试占位 Issue #9001。Issue 编号在单独审查后以常量固定在受保护的工作流和服务端；不能由评论传入。
2. 仅监听 issue_comment 的 created；拒绝 edited/deleted、PR 评论、不同仓库/owner、bot、错误工作流 ref 或其他事件类型。入口 workflow 必须来源于受保护默认分支；不加载评论中的 shell/代码，拒绝来自 fork 的可执行定义。
3. 将固定身份值从 GitHub Actions 的受信 context 获取，并交叉核对 GitHub 事件 JSON 的 repository/sender/comment/issue。**不能**从评论正文或解密后的请求推导它们。parse_event_fixture 当前只是离线验证函数，不能直接被当成已实现平台信任边界。
4. 评论正文只能包含精确的 V2 指令前缀、规范 UUID 与规范 Base64url 密文；严格长度限制和解析上限；解密后的 operation 只允许现有两项零参数主机操作，github_ci_status 永远直接用 GitHub 连接器。
5. 明确事件重放键至少包含固定仓库 ID、专用 Issue 编号、**comment ID**、jobId、nonce 和截止时间；相同评论/任务/nonce 的重复触发不能二次执行。保留消息到期、并发、SQLite 损坏和不确定结果时的默认拒绝策略。
6. 不把“任何人可上传的收件人 X.509 PEM 字符串”当成已经验证的身份。未来的加密信任设计须独立确认服务器证书、密文收件人、响应**发送者认证**（仅 CMS enveloped-data 不足以认证发送者）、签名覆盖 jobId/operation/nonce/issue/comment/时效，并使明文和私钥不出现在 GitHub 日志/评论中。
7. 只读取 host_root_fs_usage 与最小 prp_app_health，绝不读取 /api/health/runtime 原文、环境变量、任意日志/命令/URL。后台只读账户和强制命令必须与 V1 完全分离。
8. 缺少任何受信来源、单次批准、密钥、最小权限或撤销证明时，返回固定错误/未知状态，**不回退使用 V1 Shell**。GitHub 评论发布失败也不能自动重试主机调用。

### 5.4 未来有限试点的验收清单（每项必须有可检查的证据）

- [ ] 用户单独明确批准这次**真实只读试点的能力、目标主机、时间窗口和撤销方法**；不得从离线 PR 的“继续”推定授权
- [ ] 独立完成授权模式决策：是否接受路径 B 的“GH owner ≠ 聊天批准”剩余风险；或必须实施路径 C
- [ ] 静态固定专用 V2 Issue 和主线工作流；检查最小 GitHub token permissions，不复用 V1 Issue/secret/账户
- [ ] 提供真实事件来源与被伪造的 owner/ref/repository/comment/PR/edited 事件拒绝证据
- [ ] 提供证书验证、私钥保护、响应签名/认证及完整 job/nonce/comment 绑定证据
- [ ] 在独立非 root 强制命令的临时只读账号下验证无 sudo、无 Docker socket、无端口/代理转发、无任意脚本/文件读取
- [ ] 提供不确定执行、重放、并发、路径竞态、数据状态损坏与速率限制的 fail-closed 验收
- [ ] 证明可立即撤销且撤销后已排队请求不可继续生效，同时 V1 双重关闭与生产发布锁保持不变
- [ ] 受控试点真实回传与脱敏通过后，**仍需另行批准**是否长期开启

**本次评审的完成定义：** 对三层身份和授权能力不夸大；将上线门禁与可观测证据写清楚。完成本节文档**不表示**实现了可信事件适配器，也不表示安全审查或 CI 已经通过。


## 6. 2026-11-25 G3 加固及 G1/G2 协议草案（Issue #309，基于 #401）

本节仅离线候选，不改变 1–5 节门禁。原 #401 的 52/52 与 34/34 是历史精确提交证据，本候选须重新验收。

### 6.1 Replay ledger 生命周期

- 显式 initialize(path, generation) 与 claim 分离；运行态只打开已存在的文件，不创建、不迁移、不修复 schema。初始化拒绝任何已存在的文件。代际 UUID 只能由未来独立可信配置提供，禁止由评论、请求或台账本身推导。
- 原子事务校验精确 schema 与单一匹配代际；缺失、空库、错误代际、损坏、缺表拒绝，保留重复 jobId/nonce 拒绝。测试只使用临时目录和合成数据。
- **仍未解决同代际旧快照回滚**、同 OS 用户/祖先目录替换竞态、journal/WAL、磁盘耗尽、限流/保留策略。不能宣称完整防回滚。真实运行须有独立可信单调状态锚（或禁止恢复且重建前独立撤销、吊销旧代际并等待全部 180s 授权过期）；未来签名授权必须绑定新代际。恢复绝不可直接复用旧代际；没有可信状态锚或明确的撤销/重新准入证据则 NO-GO。
- 当前 generation 仅是离线状态校验，不证明请求已被该代际授权；禁止从现有 API 直接接入真实执行。

### 6.2 G1/G2 协议候选（未选型、未实现、未批准）

推荐评审路径 C：由独立用户授权签发方（必须可验证用户身份与具体操作，不能由评论或助手自行声称）签署短效授权。若尚无可用签发方，仅允许 GitHub 直接只读路径 A；路径 B 须用户另行接受 GitHub owner ≠ 独立聊天批准剩余风险，不得把 B 宣称为 C。

候选签名数据域（精确 schema，唯一版本、规范序列化、拒绝重复键/未知字段）：purpose=prp-readonly-v2-consent、issuer/keyId、subject、audience=指定试点实例及 ledger generation、repoId、专用 issueNumber、commentId（由可信事件绑定，若签发时尚未知需使用事先创建的不可执行挑战并在第二阶段绑定）、jobId、operation、parameters={}、nonce、issuedAt/expiresAt、answerCertificateFingerprint。签发者独立验证用户批准内容；固定算法与受信公钥，禁止从请求选择算法或获取任意公钥；检查撤销和时钟偏差、TTL<=180 秒。整个签名域不得由未认证 caller 伪造。签名协议具体编码/算法须独立安全评审后方可实施。

未来消费顺序：可信平台事件 -> 严格路由 -> 限长解密及证书校验 -> 独立授权签名/上下文/时效校验 -> 原子认领 -> 固定只读投影 -> 服务端独立签名结果 -> CMS 加密回传。服务端结果签名须绑定完整授权摘要、jobId、operation、nonce、commentId、实例/代际、observedAt、expiresAt、固定响应 schema。收件人解密成功不等于发送方认证；验签失败/过期/错绑定统一拒绝。回传失败不自动重试执行。

此处不选择真实签发方、不生成生产密钥、不创建监听器、不连接主机。G1–G5 保持 OPEN；HOST-PILOT-NO-GO / PRODUCTION-NO-GO。

### 6.3 Codex P2 复核修复（2026-11-25，#414）

- 不再使用 LIKE 'sqlite_%' 排除对象；精确枚举两张表、三条 SQLite 自动唯一索引及其归属/定义，拒绝其他所有对象（包括触发器、额外索引、视图、表）。
- 同一 BEGIN IMMEDIATE 事务中执行完整 integrity_check(1)，检查表与唯一索引一致性；非 ok 拒绝且不修复。临时合成数据库索引页损坏测试覆盖仍可读取表但 nonce 索引丢项的场景；不得把 quick_check 当成等价替代。
- 每次全库完整性检查存在容量/耗时风险；真正试点前仍需明确状态大小、请求频率、事务超时、资源预算与不确定执行处置。此处未完成同代际旧快照防护，G3 仍 OPEN；G1/G2/G4/G5 同样保持 OPEN。

### 6.4 有界台账与故障恢复决策（2026-11-25，离线候选）

为控制逐次完整性检查的资源使用，离线原型固定上限：主库文件及页容量 2 MiB、1024 条认领（包括已过期记录）、SQLite busy timeout 0.5 秒、认领 monotonic 预算 1 秒、每 1000 条 VM 指令检查预算且最多 500000 条 VM 指令。运行前检查物理大小；事务内先检查页容量、完整性、代际和条数；插入后再次检查页容量及时间，失败回滚且不执行采集。不自动清理或复用任何历史 nonce。以上是保守原型值，不是批准的生产配置或绝对墙钟保证；SQLite commit/fsync、锁竞争和 OS 阻塞仍须在真实隔离试点测量，journal/WAL、磁盘配额、并发入口和宿主级 watchdog 仍开放。饱和后停止准入而非自动扩大或清理。

**恢复方案 R1（推荐最小试点，尚未授权/实现真实撤销）**：禁止恢复任何旧代际台账继续接单；发现丢失、回滚嫌疑、损坏、容量饱和或不确定提交时，立即暂停入口、撤销旧代际和旧授权、停止排队及在途任务并确认静默，等待最后可能签发的授权全部过期（至少 180 秒加可信时钟偏差余量，以实际最后签发时间为准）。保留旧台账作为证据，不在原路径自动初始化。经独立审批后在新私有目录创建新随机代际并独立配置；新授权必须绑定新代际及重新批准的 operation/nonce，旧代际、过期、错误实例均拒绝；真实验收前不启用。

R1 只在可可靠发现故障并验证撤销时成立，**不能自动检测静默的同代际快照替换**。若要求自动防回滚，另需与台账不同故障域的可信、不可回退且支持原子条件更新的状态锚（R2）；必须绑定代际、单调序号和已认领状态摘要，并处理锚与本地提交之间的崩溃/不一致，默认停止执行，不能用同目录文件、SQLite 内计数或 GitHub 评论当独立可信锚。R2 未实现，不将 R1 文档当自动防回滚证明。G3 保持 OPEN；独立签名和撤销/真实隔离仍是接入前门禁。

### 6.5 独立签名授权契约原型（仅离线，2026-11-25）

- 新增 verify_consent_fixture：独立受信配置/适配器传入 issuer、keyId、subject、目标实例、代际、专用 Issue 和已存在的不可执行 challengeCommentId、已独立验证的收件人 DER 以及固定 Ed25519 验签 provider。禁止从请求或授权正文选择算法、密钥、身份或代际；与已解析请求严格绑定，要求签名正文完全等于预期规范 ASCII JSON，限制 2KiB 与 64-byte 签名，拒绝未知/重复字段、错误时效/操作/nonce/证书/实例、provider 异常。输出仅为授权正文 SHA-256 摘要，不是可执行凭据。
- 真实 Ed25519 签验仅由 test_cms_fixture.py 的临时 OpenSSL 密钥实现，无新依赖、无真实 ChatGPT 授权签发方、无在线 verifier 或执行入口。请求 PEM 解码与已独立验证 DER 相等及指纹绑定，不等于完成 X.509 链/有效期/撤销校验。测试证书为合成身份。
- 签名绑定预先存在的惰性 challengeCommentId，而不是尚未分配的执行评论 ID。未来可信适配器必须独立绑定 challenge 与实际 created execution comment、repo/issue/owner/job/nonce、一次性消费及响应签名；禁止编辑 challenge 作为执行入口。当前没有该适配器或真实 challenge，不能将合成 context 当作 GitHub 或 ChatGPT 证明。真实签发者身份、keyId 到可信公钥映射、撤销、生产 provider、跨代际授权和完整链路均未实现；不选择 B/C、不开放真实权限。
- G1/G2/G3/G4/G5 仍 OPEN；HOST-PILOT-NO-GO / PRODUCTION-NO-GO。服务端结果签名与真实信任链为后续独立工作。

### 6.6 服务端结果签名与合成离线链（2026-11-25）

- result_binding_fixture/verify_signed_result_fixture 采用独立域 prp-readonly-v2-result 和独立受信服务端 Ed25519 keyId；签名绑定已验证授权 SHA-256、原始结果字节 SHA-256、job/operation/nonce、目标实例/代际、repo/issue、challenge 与独立 execution comment、observedAt/issuedAt/expiresAt。严格要求唯一规范元数据、64-byte 签名、结果白名单 schema、授权时窗内观察与接收；错误响应也签名。签名者/公钥由外部可信配置选择，不能由回传内容选择。
- 临时签发者、服务端签名者、CMS 收件人分别使用独立合成密钥，新增 8 项回归，含错误密钥、数据及绑定篡改、非规范元数据、过期/未来观察、provider 故障以及签验→真实 SQLite 临时认领→模拟磁盘投影→独立签名→实际 CMS 加密解密→签验。没有读取真实磁盘、创建外部事件或连接主机；测试 envelope 仅为合成帧，不是上线协议。
- 尚无真实可信 issuer/服务端签名 provider、证书链/撤销、challenge 到执行评论的独立可信映射、响应一次性消费/撤销检查或生产传输适配器。相同签名回包在有效期内仍可重复验证，不能声称实现一次性消费；不允许触发二次执行。G1–G5 OPEN；HOST-PILOT-NO-GO / PRODUCTION-NO-GO。

### 6.7 可信事件映射、撤销检查与响应一次性消费（离线契约，2026-11-25）

- claim_bound_execution_fixture 先验证合成 created event 与签名授权，再精确比较由独立受信映射源提供的规范字节：repo/issue/actor/job/nonce、consentDigest、实例/代际、独立 challenge 与 execution comment、密文 token 与可信解密请求字节 SHA-256。映射不得由执行评论或请求自报；本原型不建立独立映射源、GitHub 认证或真实解密适配器。
- 同一事务内认领 job/nonce 与两类 comment ID；拒绝同一 ID 重用、跨角色交换、空缺或相等的 ID。旧低层 claim API 仍用于无 comment 的合成历史测试，不能单独接入真实执行。台账 schema 新增 purpose 与两个唯一 ID 字段；两表五条自动索引，旧 schema fail closed，不自动迁移或恢复。receipt 专用台账 purpose=receipt 与 execution 不可互换；各自独立私有路径，绑定同一授权代际但不能替代独立防回滚锚。
- consume_signed_result_fixture 在客户端签验成功后、返回任何结果前，以专用持久台账原子消费 job/nonce/comment；重复回包、错误签名、错误代际、错误台账、撤销状态未知/拒绝均 fail closed。执行与消费均于认领前后重新调用独立 active_check(scope)，只允许 exact True。authority 必须由 consentDigest/签名 scope 独立解析签发者、用户、密钥/证书、目标、代际、grant 与事件，并检查撤销和时效；合成回调不是实时可信撤销系统。认领后拒绝保留已消费记录，不自动释放或重试。
- 双检查不能消除最后一次检查与实际操作之间的 TOCTOU；真实撤销需独立原子准入/停止机制、可信时间、队列清空、并发及主机 watchdog 证据。receipt 只能证明本地消费，不能保证用户收到结果；同代际快照仍可回滚，独立防回滚状态锚仍未实现。G1–G5 OPEN；HOST-PILOT-NO-GO / PRODUCTION-NO-GO。
