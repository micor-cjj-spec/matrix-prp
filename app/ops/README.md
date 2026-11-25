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
