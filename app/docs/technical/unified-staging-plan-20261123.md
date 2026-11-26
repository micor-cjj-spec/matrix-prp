# PRP 统一 Staging 测试环境：最小收敛方案（评审草案）

- 跟踪任务：[Issue #396](https://github.com/micor-cjj-spec/matrix-prp/issues/396)
- 上游：[#323 CI/CD V2](https://github.com/micor-cjj-spec/matrix-prp/issues/323)
- 功能验收：[#260 Health V2](https://github.com/micor-cjj-spec/matrix-prp/issues/260)、[#262 UI V2](https://github.com/micor-cjj-spec/matrix-prp/issues/262)、[#301 Personal OS](https://github.com/micor-cjj-spec/matrix-prp/issues/301)
- 状态：**REVIEW ONLY / NO LIVE INSTALL / NO PROD RELEASE**（2026-11-23）
- 文档来源：GitHub 配置及 Issues 的只读审查，**未取得当前服务器、DNS、数据库、证书、外网访问或 Keycloak 的现场证据**。

## 1. 决策概要

建议**仅保留一套完整 PRP 业务系统的持久 Staging**，每个测试批次只运行一份经审查的前后端候选版本；保留 GitHub Actions 临时 Runner（MySQL/浏览器/OIDC/MCP）完成独立、可丢弃的专项 CI。统一的是**全模块业务验收入口和版本**，不是把所有数据库、OAuth Realm 和特殊故障注入测试硬合为一个共享实例。

禁止用现有 MCP V2（18082）直接原地升级为全模块 Staging；先盘点其真实数据、用户、Realm、路由和备份责任。历史 V2、legacy stage、NewDB review 只有经独立批准的迁移/退出计划才能收敛。

### 已知测试目标（配置证据 ≠ 当前运行状态）

| 类型 | 已知依据 | 运行状态 / 处置 |
| --- | --- | --- |
| 本地 dev | `app/docker/docker-compose.yml`, `app/README.md` | 本地开发模板；不代表持久 Staging |
| Legacy MCP Stage | `app/deploy/mcp-staging/compose.yaml` 仅 loopback 18081 | 旧 Compose 明示**不得直接启动/覆盖** |
| Existing MCP V2 | 历史运维/Issue 记录 loopback 18082 | 需现场核实后保留现状，绝不推断可覆盖 |
| NewDB review | `app/deploy/mcp-staging/compose.newdb.review.yaml` 18083 | 新库候选/合成 CI，未验证持久部署 |
| Actions runner | `.github/workflows/ci.yml` 与多项 MCP E2E | 临时合成测试，不等价于真实 HTTPS/iPhone |
| Production | 现有 production 环境及 `app/deploy/publication-hold.json` | 不接受 Staging 数据、路由或凭据 |

此前的 `prp-test.micor.top` / `auth-test.micor.top` 只属于历史测试 OAuth/V2 设计；是否可以用于新平台，取决于完整路由/证书/身份盘点与授权。**禁止假定 DNS 或当前主机已经就绪。**

## 2. 目标形态：一个全模块业务环境 + 多个一次性测试 Runner

```text
feature PR -> review + CI (disposable MySQL, Chromium/WebKit, OIDC)
                         |
              approved candidate (exact SHA / digests)
                         |
               full PRP STAGING (proposed)
     dedicated ingress / frontend / Spring Boot API
          dedicated MySQL + synthetic owners
       optional separate stage-only OIDC/Keycloak
          default MCP/OAuth/write integrations OFF
                         |
          verified UAT -> independent release review
                         |
               production (separate approval)
```

- 不改变现有 `首页 / 应用 / 聊天 / 我的` 四个 Tab、模块目录或已有业务入口。
- Spring Boot + Vue/PWA + MySQL 沿用现有模块化单体与构建链；暂不引入 K8s、微服务拆分、独立搜索/向量集群或新网关平台。
- 同一被验收候选必须有固定 `source_sha`、前后端工件/OCI digest、Flyway migration/checksum、运行启动时间与回滚基线。
- Staging **专用**容器项目、数据库/schema/volume、数据库账号、JWT 密钥、合成用户、DNS/TLS 和内部端口；无生产数据复制、生产备份挂载或生产密钥复用。
- 尽量在现有主机新增真正隔离的 Compose project；如当前主机容量不足或风险无法隔离，选择一台独立小型 VM。只有真实盘点后才能作成本决策。
- OIDC/MCP/ChatGPT 的真实客户端、grant、写入与外部模型发送始终为**单独审批的可选功能**。初次验收不依赖它们，不改既有 V2 的 18082/Keycloak。

## 3. 先做 S0：只读宿主与资源盘点

指定获授权的操作员，在明确指定的主机执行有限只读检查，并以脱敏报告反馈。**这里不下发 SSH、不触发服务器侧执行**。不要在 GitHub Issues/Actions 存储账户、环境变量、Token、数据库 URL 密码、密钥、私有日志或个人数据。

盘点表：

| 维度 | 需要的脱敏证据 | 阻塞条件 |
| --- | --- | --- |
| CPU/内存/磁盘 | 宿主资源、空闲容量、各 Compose 容器资源消耗 | 无法证明新增实例不影响生产 |
| 容器/监听 | 精确 Compose project 名、stage-only loopback 端口占用及进程归属 | 18081/18082/18083/11000 归属不清 |
| 数据边界 | 数据库及命名 Volume 的**名称与归属**，不读取行/密钥 | 新 Stage 误指向 `matrix_prp` 或共享 V2 |
| 入口与证书 | DNS/TLS/反代目标、Host/SNI、只读健康回执 | 当前域名被 V2 使用或 vhost 改动未批准 |
| 身份 | Realm/client/resource/issuer 的**非敏感标识**与归属 | Stage 与生产/V2 共享身份签名或账户 |
| 源码与迁移 | 真实运行 SHA/digest、Flyway 当前版本、failed/checksum 摘要 | 未核实 V30 Health / V31 Personal OS 次序 |
| 恢复能力 | 新 Stage 自身备份/销毁/重建、已有 V2 的恢复责任 | 旧 V2 停机/重建会造成未批准数据损失 |

只接受**本次真实目标主机**的证据；历史 2026-10 的 NewDB 资源检查、CI 一次性 Compose boot 不能视为当前容量或运行证明。

### S0 通过判据

- 源码/配置清单完整；所有潜在冲突标记为 `PASS/BLOCKED/UNKNOWN`，UNKNOWN 不能当 PASS。
- 说明采用同机隔离还是新增 VM 及理由、容量安全余量和预计运行成本。
- 明确旧 V2 18082、legacy 18081、NewDB 18083 各自保留/迁移/淘汰的**候选策略**，不执行淘汰。
- 记录负责人、审批责任人与 rollback 方案，只有获得独立批准才进入安装阶段。

## 4. S1–S3：部署定义与候选构建（不等于安装）

拟在**后续单独 Draft PR**新增 `app/deploy/unified-staging/`，经独立代码审核后交付：

1. stage-only Compose 或最小容器定义，显式命名独立项目、volume、network、loopback listener，不引用任何生产或 V2 容器/网络/DB credential。
2. `.env.example` 只出现占位符，真实 secret 由授权安装人员单独生成；拒绝空值、默认密码、共享的 `matrix_prp` schema 和生产 hostname。
3. `preflight`：**只读**验证端口、DNS/TLS、磁盘、候选 SHA/digest、外部服务标志、数据库 namespace 和 Flyway 期望；任何不明项 fail-closed。离线自述校验须标明 `static_only=true`。
4. stage-only `install / check / rollback` Runbook，部署操作只在审批后受控执行；不得复用生产的 SSH/controller 成为通用远程 Shell。
5. test-only seed 两个合成 owner，明确重置策略，拒绝复制真实健康、财务、对话或视频数据。
6. 版本化 `stage-status.json` 由可信真实部署/巡检过程写入；未取得真实回执时只允许 `PROPOSED` 或 `BLOCKED`，不能伪造 `VERIFIED`。

候选集成须遵循 feature→dev→main 治理；当前 dev protection 与 required checks 仍需独立核查/批准。联合 CI-only PR（例如 #385、#342）**只能证明兼容，不能当作默认可发布源**；真实 Staging 需要经过审核的功能候选 exact SHA，并确认 Health V30 / Personal OS V31 的迁移策略无冲突。

## 5. S4：一个 Staging，按模块检查

| 验收域 | 最低真实验收 | 与已有任务复用 |
| --- | --- | --- |
| 全站导航与 UI | 四 Tab、所有原业务入口、桌面和移动布局、键盘/缩放/主题、旧功能不丢失 | #262、#177 |
| 后端/数据库 | 真正 HTTP API、MySQL/Flyway 当前 checksum、重启/回滚、跨 owner 403 | #260、#301 |
| 健康中心 | 合成 meal / exercise / weight / goal CRUD、营养未知值、7/30/90 天和幂等 | #260、#177、#178 |
| 个人智能 OS | 合成事实/目标→任务/复盘证据链、取消无写入、撤销/权限边界 | #301、#188 |
| 学习/视频/复盘 | 既有模块菜单/列表/详情与原有数据隔离，按实际候选代码覆盖 | #218 及现有回归 |
| MCP/OAuth | 初始默认 OFF；仅在单独获批测试客户端/owner/scopes 时做真实授权、拒绝和撤销 | #149、#178、#218 |
| 真机 | 实际 iPhone Safari、安装 PWA、网络异常/超时/恢复、可核实截图（脱敏） | #177、#262 |

每个测试结果需记录：
`case_id | PASS/FAIL/BLOCKED | stage_alias | deployed_sha | digest | schema_version | tester_alias | test_utc | redacted_evidence_ref | defect_ref`。

只有**已合入、真实运行并完成测试**的功能可以标记 PASS；未合入仍应为 BLOCKED/NOT_IN_CANDIDATE，不作假阳性。

## 6. 状态与发布边界

统一 `stage_status`：`PROPOSED` → `RESOURCE_APPROVED` → `DEPLOYED_UNVERIFIED` → `VERIFIED`；另有 `BLOCKED`、`FAILED`、`RETIRED`。仅审查文档、GitHub CI 通过或有 `docker compose config --quiet` 的预检都不是 `DEPLOYED_UNVERIFIED` 或 `VERIFIED`。

- `CI_PASS`：目标 commit 的合成自动化已通过。
- `STAGING_VERIFIED`：独立 TLS/Web/API/DB/合成用户及规定 UAT 在**实际安装版本**通过。
- `PRODUCTION_READY`：另行核查备份、真实生产迁移演练、分支保护/审批及其他发布门禁。
- `PRODUCTION_LIVE_VERIFIED`：只能通过生产已运行版本/健康/数据完整性证据确认。

必须保留 `app/deploy/publication-hold.json`。此文档不授权更改 `main`、`dev`、Nginx、DNS、SSH、任何 MySQL/Keycloak 实例或 MCP scopes/写权限。

## 7. 下一步交付及负责人界面

- **当前 Draft：** 仅本决策文档 + Issue #396，无真实宿主/代码变更。
- **后续 S0 受控只读阶段：** 授权运维提供脱敏现实环境清单；GitHub 会话核对配置与现场清单。
- **后续 S1：** 在同机隔离与独立 VM 之间做资源决策，批准具体网络、存储、身份边界。
- **后续 S2：** 独立 feature/Draft PR 交付受检的 Stage Compose、preflight、测试数据与文档，先在一次性 CI 中验证。
- **后续 S3–S4：** 经明确批准才构建/安装持久 Staging；跨模块真实 UAT；关联 #323 的受控生产发布，但不自动推广。

**最终状态：截至本文提交，宿主尚未现场核查，Staging 尚未由本任务安装；一切真实环境验收仍为 NO-GO。**
