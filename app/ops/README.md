# PRP 预授权状态快照 D-P0（离线）
关联 #309 ADR-V2-03。D-M01/M02：合成输入固定指标投影、严格 schema、临时目录原子快照、时效判定。没有定时任务、真实主机采集、网络请求、MCP server/工具注册或 OAuth 变更。CI PR-only contents: read，临时文件均在测试中创建。旧 #414 保持冻结。
- CPU 聚合 /proc/stat 八字段差值，guest 不重复计入，idle+iowait 为非 busy；首轮/计数回退 unknown。尚需真实启动标识、采样间隔、采集超时与隔离证明。
- 内存 MemAvailable；根盘 freeBytes 为非 root 可用，不含保留块；健康 5xx 为 probe_error，不推断主机 down；readiness 固定 unknown。不回传原始 JSON、路径、配置、版本或凭据。
- 单环境 staging 合成契约；120 秒到期（含边界），未来容差 5 秒，损坏/缺失/不可信则 unavailable，stale 丢弃指标。fresh 仅代表快照时效，并非服务正常。
- 存储原型只允许受信任的绝对目录、逐级 no-follow、同 UID 0700/0600，固定 status.json、原子替换及 fsync。临时目录的同 UID 测试不证明真实 writer/reader 账户隔离或不可篡改；M04 应设计独立所有权和 reader 只读挂载。未实现真实采集调度、资源限制、时钟保障或实际部署。不能用当前 class 直接开放 API。
- D-M03 仍需独立 OAuth resource/audience、固定 scope、owner/grant 与撤销校验，默认关闭，禁止 legacy OAuth-off 路径。禁止注册或暴露真实工具。D-M04/05/06 未验收；不接入主机、不部署、不合并、不改现有业务与发布锁。

Atomic replacement readers validate nlink==1; an opened old inode unlinked before fstat is conservatively unavailable, not partially returned. O_EXCL collision never cleans up a file the invocation did not create. Actual reader/writer isolation and scheduler single-writer enforcement remain M04.
