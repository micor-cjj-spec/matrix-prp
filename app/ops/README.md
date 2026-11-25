# PRP 预授权状态快照 D-P0（离线）

关联 #309 ADR-V2-03。D-M01/M02：合成输入固定指标投影、严格 schema、临时原子快照、时效判定。D-M03：零参数查询与合成 identity/grant 授权契约。D-M04：固定源采集运行时、单实例锁、分离 UID/GID 快照读写、systemd disabled-by-default 模板。没有 MCP 网络服务或真实 OAuth adapter。

- CPU 聚合 /proc/stat 八字段差值，guest 不重复计入，idle+iowait 为非 busy；首轮/计数回退 unknown。内存 MemAvailable；根盘 freeBytes 为非 root 可用，不含保留块。
- 120 秒快照 TTL、未来容差 5 秒；损坏/缺失/不可信则 unavailable，stale 丢弃指标。fresh 仅代表快照时效，不代表主机或应用健康。
- 真实采集仅允许固定 /proc/stat、/proc/meminfo 和 statvfs("/")，CPU 两次采样间隔 1 秒；无网络、健康 HTTP 探针、Shell、DB、Docker 或用户指定路径。应用 readiness 保持 unknown。
- writer `prp-ops-collector`，reader `prp-ops-mcp`，共享组 `prp-ops-snapshot`；目录 writer:group 2750，快照 writer:group 0640。reader 必须是不同 UID 且仅通过共享组读。共享读写边界由独立类实现。
- systemd service/timer 仅模板，均要求 root-owned `/etc/matrix-prp-ops/ALLOW_HOST_METRICS` 精确内容 `host-metrics=approved\n`；timer 未启用。模板未安装、启动或在目标主机验证。代码 main 同样检查 marker。
- M03 synthetic issuer/resource 为 .invalid；无真实 JWT/JWKS/OAuth/MCP listener/grant service。无采集调度以外的远程调用。
- M04 静态及临时目录测试不证明真实系统用户、目标机 systemd sandbox、时钟或部署可用性。M05/06 未完成/未授权。#414 继续冻结；不接入主机、不部署、不合并、不改生产锁。

## D-M05 Offline MCP surface contract
- `mcp_adapter.py` describes exactly one fixed tool, `prp_ops_status_get`, with empty-object input schema and MCP readOnly/destructive/idempotent/openWorld annotations. `tools_call` accepts only the exact tool and empty arguments, discards request metadata, and delegates to the M03 identity/grant checks and M04 read-only reader. Errors are uniform. Tool annotations are descriptive, never authorization.
- `ServerVerifiedContext` is a future server-side object; current tests inject synthetic providers only. There is no JSON-RPC server, HTTP listener, OAuth middleware, JWT/JWKS verifier, grant database, MCP app registration or public route. This module must not be mistaken for a working ChatGPT connector.
- M05 synthetic tests exercise tool discovery, empty calls, parameter spoofing, metadata spoofing, disabled policy, revoked grant, stale snapshot and output minimization. Live transport remains blocked on independent OAuth and M06 approval.

- Host-wide CPU/RAM/root-disk collection is explicitly gated by root-owned `/etc/matrix-prp-ops/ALLOW_HOST_METRICS` exact content `host-metrics=approved\n`; this is a disclosure authorization, not just a service enable flag. Marker absent by default; shared production/staging host requires separate explicit approval.

## D-M05.1 独立鉴权与 JSON-RPC 接入候选（离线）
- 现有 McpClientGrantService 依赖业务数据库，McpOAuthResourceServerConfig 还依赖业务账号与身份链接；方案 D 独立服务不能直接依赖它们。候选采用 RFC 7662 introspection（单独 confidential resource client，TLS 证书/主机名校验、固定 URL、无 redirect、响应限长）与独立管理员持有 grant.json，避免手写 JWT 验签。HTTPS 连接仅对 .invalid fixture，测试全部 mock；不触达真实 issuer，不申请真实 client、不写入凭据、不变更 Keycloak。真实 issuer 的 introspection 权限、响应字段及 scope/audience/client profile 需 M06 前独立确认。
- grant.json 默认 /etc/matrix-prp-ops/grant.json，root 所有、reader group 0640、目录 0755，固定 schema、单硬链接、无 symlink、只读且每次重读。授权 ID 从管理员记录产生，不信任 token/model 传入的 grant ID；token iat 必须严格晚于新 grant issuedAt（同秒也拒绝），避免秒级时间无法区分授权先后的歧义。撤销 active=false 或移除文件；仅提供 reader，未实现管理员授权 UI/写入/签发或真实持久授权流程。真实路径祖先、UID/GID、文件原子发布及备份回滚策略仍需审查。
- Bearer token 通过独立 TLS introspection 获取 active/iss/sub/aud/client_id/azp/token_type/scope/iat/exp/nbf，严格固定单 audience、唯一 ops scope、双 client 一致、明确时间；不透传 claims，不缓存跨请求，不记录 token。一次 introspection 加本地 grant 前后检查；已开始请求的最后检查到响应交付之间仍有残余竞态，未宣称瞬时撤销。
- rpc_adapter.py 仅 in-process candidate：有界严格 JSON-RPC envelope，支持仓库现有 2025-06-18 initialize、ping、tools/list、tools/call、initialized notification；所有入口先鉴权，无批处理、路径或命令参数。不是 HTTP server，未验证 Streamable HTTP header/Origin/Accept、重复 Authorization、并发配额、传输超时、协议协商、真实客户端互操作。保留 M06 阻塞，不自动启动。

## D-M05.2 HTTP 入口、预算及脱敏审计（离线）
- http_boundary.py 仅接受可信 ingress 传入的原始 header pairs、精确 target 和有界 body；未监听端口。固定 .invalid Host、/mcp POST、RFC 9728 resource metadata GET 路径及 401 challenge；拒绝重复安全头、错误 Origin、路径别名、转发分块、压缩及 session ID。仅支持固定 2025-06-18 JSON 响应子集（Accept 同时包含 JSON/SSE），不是完整 Streamable HTTP 实现。真实 TLS、原始 header 保留、连接/请求体读取超时、代理和 ChatGPT 互操作仍需单独验收。
- 单进程全局滚动窗口 60 请求/60 秒（含未授权）、4 个并发（名额保持至审计与最终披露判断完成）；内存有界、单调时间回退拒绝；不依赖可伪造请求头或动态用户桶。恶意请求可耗尽全局配额，非分布式限流；真实入口需独立限额、连接管理与拒绝服务验收。
- 每次请求构造固定审计事件（随机 traceId、固定 route、candidateStatus、outcome）；不记录 token、用户输入、JSON-RPC id、原始指标。审计 sink 由服务器注入，失败返回 503，不泄露数据。无持久日志实现；最终披露检查可能改变 HTTP 结果，审计仅记录检查前候选结果，不是响应交付证明。真实审计持久性与主体归属、写入时间、采集与读取超时仍待实现。
- 读取入口也要求 root-owned ALLOW_HOST_METRICS 门禁（调用现有校验函数），防止仅停采集后仍返回未过期快照；请求前、dispatch 后、审计后均校验。最后检查到实际网络发送仍有竞态。合成测试注入 marker，不创建真实文件。新增完整 HTTP->Bearer introspection->grant->RPC->snapshot 测试。无真实 MCP 服务注册、真实端口监听或主机访问。

## D-M05.3 管理员授权生命周期与本地持久审计（离线）
- 修复 P2：HTTP header 在类型检查后、字符扫描或 regex 前先做累计长度与 key 长度校验；5M 字符输入回归不依赖计时，直接证明扫描未调用。
- admin_grant.py 为离线管理员候选，不注册 MCP 工具或 CLI。要求独立审批标志与可信 admin UID/GID、固定 schema、预置 inactive seed 和独立 0600 lock；缺失/错误状态不自动创建。非阻塞 flock 下比对完整旧记录 SHA256 再原子替换 0640 grant.json，fsync 文件与目录。issue 仅在撤销/过期后，renew 仅有效 grant，均轮换 UUID 和 issuedAt；单次授权候选最长7天；revoke 保留原 ID/时效的 inactive tombstone。需独立管理员真实审批与初始化；不能将 approved=True fixture 当作真实人类批准。未提供真实初始化、CLI、自动续期、OAuth grant 撤销或备份回滚保护；未知 commit 不可自动重试，需人工核验。独立 OAuth token 需新 iat 严格晚于轮换授权时间。
- audit_store.py 为本地 JSONL 持久候选，预置 0700 目录/0600 单链接普通文件，固定字段与 recordedAt，非阻塞独占锁、1MiB 硬容量、单次 append+fsync；缺失、链接、权限、容量、部分尾记录、锁竞争、写入或 fsync 失败均拒绝返回，不自动清理/创建/截断。fsync 失败可能已写入，非交付证明；当前 UID 可修改文件，非防篡改、非独立审计。真实服务需审计保留/轮换、告警、磁盘空间、独立可信主体归属与防 DoS 验收；拒绝请求的审计也可能耗尽容量，不能直接启用。审计全量字段不含 token、原始指标或请求数据。没有真实文件/账号/授权变更，测试使用临时目录。
