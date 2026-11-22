# #218 独立复盘/视频 MCP 只读 Canary：实施前核查与验收方案

> **阶段：PREPARATION ONLY / NO DEPLOY / NO GRANT / NO MAIN MERGE**  
> 准备范围于 2026-11-22 获用户同意：仅允许代码仓库内的方案、离线审查和验收/回滚清单准备。**未批准**启动主机容器、公开路由、安装 Keycloak 客户端、变更真实 Scope/owner grant、执行数据库备份/迁移、连接真实 ChatGPT 账号或发布生产。后续每项有状态变更的动作都要单独授权。

## 1. 唯一目标与当前证据

这项 Canary 用于真实验证三个**只读**工具：

| MCP 工具 | OAuth Scope | 输出限制 | 必须排除 |
| --- | --- | --- | --- |
| `prp_reviews_list` | `prp.reviews.read` | 最多 20 条 owner-scoped 复盘摘要 | 完整复盘、高亮/问题/行动正文 |
| `prp_video_folders` | `prp.video.read` | 最多 50 个 owner-scoped 文件夹 | 他人目录 |
| `prp_video_progress` | `prp.video.read` | 最多 30 条 owner-scoped 视频元数据和进度 | 上传内容、媒体文件、播放 URL、票据 |

- 当前已完成工程验证：Draft #219 `4114e915eb5c1499bb7e66d8f0583e7ae29a8318` 的 CI [34/34](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44983915912)；Draft #224 `7843f239aaae3d2d723f848dd04582b56465b3f3` 的 CI [35/35](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44983924740)；Draft #278 `6367db748e347cee18f185e6f4fefdb42946437b` 的 CI [35/35](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44983929742)。均为**合成/隔离 CI**，不是当前真实 ChatGPT 连接验收。
- [#149 的实际运行证据](https://github.com/micor-cjj-spec/matrix-prp/issues/149#issuecomment-7072097863)：当前公网 `prp-test.micor.top` 接向 V2 `127.0.0.1:18082`；第九份 Compose overlay `expanded-image.yaml` 使其实际声明 **8 项 Scope** 且 `WRITE_ENABLED=true`。V2 正承载其他测试目的，**不得通过删覆盖文件、关写开关、改 Client 或回退至 `18081` 来满足本任务**。
- [只读公网探测](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44983925753) 对 #149 严格 task-only 合同返回 `PUBLIC_METADATA_ACCEPTANCE=NO_GO`；但 OIDC 发现正常。这是**既有 V2 的 Scope 不匹配**，不能当作 #218 已部署或 OAuth 连接失败的证据。
- `app/deploy/mcp-staging/compose.yaml` 是 `18081` / `prp-test` 的旧模板；`app/deploy/mcp-oauth-stage/compose.yaml` 又复用该旧项目及 `auth-test` 地址。它们可作为隔离模式的**只读参考**，**不得不经改造核验直接运行/复制**用于 #218 独立 Canary。

## 2. 隔离目标设计（待审批，不表示资源已存在）

采用**独立非生产主机或专门隔离的资源环境**，优先全独立实例，不复用当前 V2、旧 stage 或生产服务：

| 资源边界 | 准备要求 | 当前状态 |
| --- | --- | --- |
| 目标主机/命名空间 | 专有 Compose project、网络、容器、卷和启动账号；禁止共享 `prp-mcp-v2`、`prp-mcp-stage`、`prp-mcp-oauth-stage`、生产 `matrix-prp` | **待指定和核实** |
| PRP 数据 | 全新独立 MySQL schema/volume；仅两个及以上合成测试 owner、复盘与视频进度数据；不接入生产 `matrix_prp`、V2 真实数据/备份、共享视频目录 | **待实施审批** |
| OAuth 数据 | 单独 Keycloak Realm/实例 + 独立 Postgres/密钥/备份回滚；不能更改目前运行的 `auth-test` Realm、原有 client/policy/JWKS | **待指定和核实** |
| MCP Resource | 新的、唯一的、公开可信 HTTPS 资源 URL，精确路径 `/api/mcp`；**不得使用** `https://prp-test.micor.top/api/mcp` | **域名、证书、路由均待审批** |
| Issuer/JWKS | 与新资源对应的独立 HTTPS Issuer / JWKS；Token `iss` / `aud` 严格绑定此新资源，不接受当前 V2 的 audience | **待审批** |
| 流量与暴露 | 后端/MySQL/Keycloak DB 只在隔离网络；对外仅审批的最小 HTTPS MCP、resource metadata、OIDC 和第一方登录/回调路由；无生产 Nginx reload 或通配 `/api/**` | **待审批** |

**占用确认是强制门禁**：在部署审批前，不假定目标端口、DNS、证书、内存、磁盘或主机已可用；必须核实实际监听归属、容器名称/卷、DNS 记录及公开路由。禁止自动重定向已有 `18081`、`18082`、生产 `11000`，禁止 `docker compose down -v` 清理任何共享项目。

## 3. 最小权限与工具目录验收契约

建议 Canary **OAuth 资源声明 Scope** 精确为 `prp.reviews.read`、`prp.video.read`；OIDC 协议参数（如 `openid`）单独按授权方要求审查，不得默认为 PRP 数据 Scope。不要从 V2 复制已有 8 Scope；也不要误将 #149 的 `prp.tasks.read` task-only 合同认定为这次通过。

| 属性（仅拟定配置，不可直接应用当前 V2） | 隔离 Canary 验收值 |
| --- | --- |
| `MATRIX_PRP_MCP_ENABLED`, `MATRIX_PRP_MCP_OAUTH_ENABLED` | 独立部署获批后 true；部署前不动任何现有环境 |
| `MATRIX_PRP_MCP_WRITE_ENABLED` | **false** |
| `MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES` | **`prp.reviews.read,prp.video.read`**（按后端实际解析格式验证） |
| `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED` | **false**：不暴露不相关任务、健康/记录/刷题扩展工具 |
| `MATRIX_PRP_MCP_REVIEW_VIDEO_READ_TOOLS_ENABLED` | 初始 **false**；仅在单独部署/启用审批后置 true |
| 工具枚举 | 获批启用后，**恰好** `prp_reviews_list`、`prp_video_folders`、`prp_video_progress`；无任务、财务、健康、写入/审批工具 |
| Grant | 独立合成 owner、独立 client 的**完整** Scope 集经 owner 显式认可；`POST /api/mcp/clients` 是**全量替换**，不是增量追加 |
| 身份/行为 | Issuer、resource audience、client、owner link、token scope、实时 grant 均需通过；仅 owner 的有界只读 SQL 查询 |

**重要的分阶段特性**：在开关仍为 false 时，三项工具必须全部不可枚举；打开开关而不发放相应 token/grant 仍不得授权调用。资源 metadata 的 Scope 声明不等于已发放权限。若三项之外出现其他 MCP 工具，即使当前不可调用，**目录隔离验收失败**。

对于真实 ChatGPT OAuth，`client_id` 必须以实际 ChatGPT 流程和官方 `https://chatgpt.com/oauth/client.json` 约定核验，并逐项核对回调、PKCE S256、受限 `private_key_jwt` / CIMD、`resource` 与 Issuer；需要时单独审批 `prp-first-party-link`。**不得为了“跑通”启用通配重定向、无边界 DCR 或共享 Realm 客户端变更。**

## 4. 前置证据清单（全部满足后才允许申请“部署/连接”审批）

- [ ] 独立测试资源清单：主机/命名空间、owner、网络、项目/卷名、资源预算、真实监听占用（仅脱敏标识）。
- [ ] 新的 MCP Resource、Issuer、JWKS、精确回调和 TLS 证书信任链；DNS 与公开反代隔离证明。不得是当前 `prp-test` / `auth-test`。
- [ ] 独立数据源的隔离证据：无真实用户记录、无生产/现有 V2 数据卷/账号/备份挂载；合成双 owner 种子方案。
- [ ] 针对**新测试目标**的明确 G0/B2 变更边界、授权主体、备份与**真实独立恢复**记录、完整回滚计划及有效批准凭据；不得捏造或复用旧 `*.safe.json` 收据。
- [ ] exact SHA `6367db748e347cee18f185e6f4fefdb42946437b` 与三层 Draft 依赖/默认关闭开关复核；新构建时需复跑相应 exact-head CI。
- [ ] 经独立审查的客户端和 Scope/owner grant 完整前后快照（脱敏，**不记录**访问令牌、密码、用户笔记）。
- [ ] 明确的**单独部署审批**、公开路由/Keycloak 改动审批以及真实 ChatGPT 账号授权与撤销测试的**单独用户同意**。

以上缺一项则**NO-GO**。当前用户批准的是准备工作，**不能勾选**任何尚未由操作人员或验收人实际完成的项目。

## 5. 拟执行的正式验收矩阵（全是待办，不是既有结果）

| 检查 | 期望 | 当前 |
| --- | --- | --- |
| 未启用时 `tools/list` | 三项 review/video 工具均不出现 | 未执行 |
| 只声明/不授予 Scope | 无授权可调用，严格拒绝 | 未执行 |
| 精确授权后 `tools/list` | 仅三项只读工具，安全 annotations/Scope 正确 | 未执行 |
| 合成 Owner A/B | A 仅见 A 的复盘与视频，跨 owner/folder 请求拒绝 | 未执行 |
| 边界/负例 | 20/50/30 行上限；非法 ID/日期/过滤器；软删除、分页、视频媒体/播放/upload 不可获取 | 未执行 |
| 真实 ChatGPT OAuth | 实际 Connect、官方 Client Assertion、Issuer/Resource/PKCE、owner link，可用 token | 未执行 |
| 撤销 | 撤销 Scope 或 grant 后**立即拒绝**新增读取；合法原权限不被破坏 | 未执行 |
| 回滚 | 独立开关 OFF；三工具消失；还原经用户确认的完整 grant 与原 Scope/Realm/路由；旧 V2/生产无变化 | 未执行 |

验收时先看**脱敏状态码、工具名、Scope 名、SHA 和时序**；不要把复盘正文、个人信息、Video URL、JWT、Cookie、密钥或回调 Code 写到 GitHub Issues/CI 日志。

## 6. 严格回滚边界与停机条件

1. 测试中发现任何额外写工具、越权返回、错资源 audience、共享 V2 命中、私密数据泄漏或无权限访问，应立即停止此**独立 Canary**的后续步骤，并按获批的隔离回滚方案处理，不触碰原有 V2。
2. 单独获批后，优先把隔离 Canary 的 `MATRIX_PRP_MCP_REVIEW_VIDEO_READ_TOOLS_ENABLED` 设回 false 并验证三工具不可枚举；该开关与 `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED` **不是同一个开关**。
3. 还原**新 Canary**原始 Scope 配置和精确 client 的**完整原授予集合**，必须取得 owner 确认；不得只提交两项新 Scope、清空整个 client 或撤销已有 V2 的授权。
4. Keycloak/反代/容器撤销仅限独立批准的资源和可验证恢复方案。不得删除共享客户端、签名密钥、数据库、卷或回滚系统已有多权限测试配置。
5. 通过非生产只读测试不等于可以合并 main 或上线生产；另需正式评审/授权。

## 7. 来源与本次准备边界

- 代码门禁：`app/backend/src/main/java/com/matrix/prp/mcp/McpToolConfiguration.java`、`McpOAuthMetadataController.java`、`app/docs/technical/mcp-phase2-review-video-oauth-gates.md`（基于 Draft #278 HEAD）。
- 旧环境设计参考：`app/deploy/mcp-staging/README.md`、`compose.yaml`、`check_env.py` 与 `app/deploy/mcp-oauth-stage/README.md`。这些文件**没有**提供本独立 Canary 可直接执行的部署方案。
- G0/B2 边界：`app/deploy/mcp-oauth/keycloak-resource-guard/G0-EXACT-CLIENT-DELTA-REVIEW-20261027.md`、`B2-RELEASE-GATE.md`，原任务 #149 保持独立 NO-GO。
- **本文件仅是可审查的准备工件**：未创建主机/域名/容器/测试用户，未备份、未签发凭据、未连接真实 ChatGPT、未改变权限或分支发布状态。


## 8. 只读计划配置静态门禁（离线、非部署）

已增加 `app/scripts/mcp218-canary-plan.mjs`，只验证**尚未部署的非密钥 JSON 方案**中的命名隔离、最小 Scope、工具名单及安全开关，不访问网络/主机/数据库，也不创建或修改任何资源。它不能证明实际 DNS、网络、Volume、端口、issuer 或 Keycloak 安全，不能替代独立审批，也不提供部署命令。

自检可在任何拥有 Node.js 22 的本地工作区执行：

```sh
node --test app/scripts/mcp218-canary-plan.test.mjs
node app/scripts/mcp218-canary-plan.mjs /path/to/private/nonsecret-canary-plan.json
```

**第二条命令需要在单独准备的、无任何密码/JWT/私钥/令牌的 JSON 计划上执行**。这些配置项必须全部具备：

- `purpose: "mcp218-review-video-readonly"`、`release_gate: "PREPARATION_ONLY"`。
- `project` 使用全新 `prp-mcp218-...` 项目名，`mysql_schema` 使用独立 `matrix_prp_mcp218_...`，`mysql_volume` 和 `keycloak_volume` 使用彼此不同的 `mcp218_...` 名称。
- `resource_url` 必须是新的可信 HTTPS 域名加 `/api/mcp`，`issuer_url` 是**另一域名**加 `/realms/prp-mcp218`。禁止旧 `prp-test.micor.top` / `auth-test.micor.top`、生产域名（特别是正式 OAuth 入口 `auth.micor.top`）、localhost、裸 IP 和示例域名。为避免与 #301 等其他线程的预览环境混淆，本 Canary 方案要求 Resource 域名的首个 DNS Label 以 `mcp218-` 开头，Issuer 以 `auth-mcp218-` 开头；这种命名仅表示规划意图，不构成真实域名所有权证明。**静态通过不证明 DNS 已存在或真实证书有效**。
- `database_source: "new-empty"`、`keycloak_source: "new-empty"`、`data_policy: "synthetic-only"`。
- `published`、`mcp_enabled`、`oauth_enabled`、`write_enabled`、`additional_read_tools_enabled`、`review_video_read_tools_enabled` **全部为 JSON 布尔 `false`**，任何提前激活均拒绝。
- `advertised_scopes` **严格且仅有** `["prp.reviews.read", "prp.video.read"]`；`expected_tools` **严格且仅有** `["prp_reviews_list", "prp_video_folders", "prp_video_progress"]`。
- 禁止出现任何额外 JSON 字段，包括 `client_secret`、数据库口令或原始凭据。失败输出仅使用固定错误代码，不回显配置值。

脚本成功时只会输出 `MCP218_PLAN_SHAPE_PASS_ONLY_NO_DEPLOY_AUTHORIZATION`；失败输出 `MCP218_PLAN_NO_GO` 和错误分类，退出码为 2。这个通过标志**绝不是** `approved-install.safe.json`、`fresh-b2-restore.safe.json`、真实 G0/B2 审批或上线许可。

离线安全测试现包含 36 项：原有 30 项函数与 CLI 组合检查，再覆盖 6 种生产 OAuth 与跨工作流主机名复用的拒绝路径。所有自动测试必须以**最新确切提交**的 GitHub Actions 结果为验收证据，不能继承旧 SHA 的成功状态。真实的 Compose 渲染、网络资源占用、受信任证书、恢复演练、owner 授权与撤销仍全部为**独立待办**。


## 9. 独立 Realm 候选：纯内存生成与明确阻塞

现有 `app/deploy/mcp-oauth/build_realm.py` 生成的旧 `prp-mcp` Realm 默认含 `prp.tasks.read`、财务、健康及写入 Scope，原 `review_exact_client_registrations.py` 也固定旧 `prp-test` Resource 和 task-only Client。这两者**不是 #218 Canary 可直接使用的模板**。

已新增 `app/deploy/mcp218-canary/review_realm.py`，仅提供 `build_review_video_candidate(resource)` 纯内存函数，复用旧构建器的基础安全默认和 `basic` 受签名身份映射，但把新候选：
- Realm 精确定为 `prp-mcp218`；不触及原有 `prp-mcp` Realm。
- Data Scope 精确定为 `prp.reviews.read`、`prp.video.read`，另保留 OIDC 必需的 `basic` 身份 Client Scope；**不生成**任务、财务、健康、写入、离线持久化授权 Scope。
- 唯一 Client 为 bearer-only `matrix-prp-mcp218-resource`，绑定传入的新 `https://mcp218-.../api/mcp`；没有 ChatGPT 登录 Client、Keycloak 管理员、回调 URL、测试用户或 owner grant。
- 拒绝现有域名、非 HTTPS、非精确 `/api/mcp`、携带密码/端口/query/fragment 的 URL，以及不符合 `mcp218-` 命名的目标。

**重要：此函数不生成可直接部署的包，不提供安装入口，也不执行任何文件/网络写操作。** 它的通过证据只能证明可构造候选 Realm JSON 结构，不能证明 Keycloak 接受导入、真实 Issuer/JWKS 可用、OpenAI client 能签名、PRP owner-link 已工作；这些继续是**独立环境真实审批及 E2E**，没有取消 #149 或 G0/B2 阻塞。

新的 Python unittest 专项检查 Realm/Scope/Client 数量、无第三方登录 Client、无旧任务权限、OIDC subject 安全映射、不修改原构建器、不访问网络、旧域名/注入拒绝和上游构建器结构漂移。离线 Node.js 方案校验与 Python Realm 候选均拒绝 DNS 标签长度超过 63 或完整主机名超过 253 个 ASCII 字符，边界测试覆盖 253 字符允许、254 字符拒绝；仅证明静态语法一致性，不证明 DNS 实际可用。GitHub Actions 中以 `python3 -m unittest discover -v -s app/deploy/mcp218-canary -p 'test_review_realm.py'` 执行，**必须以当前 SHA 最新实际 CI 完成结果为准**。


## 10. 同一份计划的跨语言离线一致性预检（不部署）

前述 `mcp218-canary-plan.mjs` 和 `review_realm.py` 单独通过，不能证明两者对于**同一份非密钥计划**输出完全一致。子 PR #312 增加 `app/deploy/mcp218-canary/check_offline_contract.py`，仅执行本地 Node.js 计划校验，再**在内存中**调用独立只读 Realm 候选，检查：

- Node.js 方案语法与安全开关全部 PASS；Python 使用**同一 Resource URL** 生成候选；
- Realm 固定 `prp-mcp218`，唯一 bearer-only `matrix-prp-mcp218-resource` 的 `resource_url` 与计划完全一致；
- Realm 含 `basic` + 计划指定的两个复盘/视频只读 Scope，不能出现额外 client、真实用户、secret 或 credentials；
- 缺失/超过 64KiB 的计划、非法 JSON、缺失 Node、超时、Scope/Resource 不符一律固定错误码 NO-GO，不回显 JSON、用户笔记、Token、客户端凭据。

本地只读执行（需 Python 3 和 Node.js 22，传入**无凭据的待审批计划 JSON**）：

```sh
python3 app/deploy/mcp218-canary/check_offline_contract.py /path/to/nonsecret-mcp218-plan.json
```

成功只返回 `MCP218_OFFLINE_CONTRACT_PASS_ONLY_NO_DEPLOY_AUTHORIZATION`；失败返回 `MCP218_OFFLINE_CONTRACT_NO_GO` + 固定分类码，并以退出码 2 结束。该命令**仅读本地配置、执行本地 Node 校验和构建 Python 内存对象**；不访问网络、不写磁盘、不导入 Realm、不提供可安装配置或审批凭据。GitHub Actions 用合成计划和负例测试覆盖该链路；与真实 DNS/TLS、Keycloak Client、ChatGPT 登录、G0/B2 及环境部署没有任何等价关系。上述实际验收仍全部 NO-GO，只有获得单独批准才可继续。


## 11. #218 独立登录 Client 与合成账号白名单评审（未安装、未授权）

已新增纯内存 `app/deploy/mcp218-canary/review_exact_clients.py` 和对应的 `test_review_exact_clients.py`，在已存在的**单一 bearer-only Resource Client 候选之外**，仅为独立 `prp-mcp218` Realm 准备**两份不具备导入能力的评审提案**：

- ChatGPT Client ID 精确为 `https://chatgpt.com/oauth/client.json`；回调精确为 `https://chatgpt.com/connector_platform_oauth_redirect`；Client JWT + 官方 JWKS `https://chatgpt.com/oauth/jwks.json`，PKCE S256；audience mapper 仅绑定传入的新 `mcp218-*/api/mcp` Resource。默认 OIDC `basic`，可选数据 Scope 严格只有 `prp.reviews.read`、`prp.video.read`。未加入旧任务、财务、健康、写入权限，也不默认追加 `offline_access`。
- 独立 Realm 内第一方客户端的 **Client ID 必须固定为 `prp-first-party-link`**：这是现有 PRP SPA `checkedFirstPartyAuthorizeUrl()` 的不可放宽安全校验值（原候选 `prp-mcp218-first-party-link` 会被浏览器拒绝）。**仅在全新 `prp-mcp218` Realm 中复用标识字符串，不复用 V2 的真实 Client 对象、密钥、用户或 Grant**；公开 PKCE S256，回调仍唯一绑定新 Resource Origin `/prp/me/mcp-link/callback`，不包含数据 Scope。未来获批的独立环境必须在新 Resource Origin 提供独立 PRP SPA，且构建时 `VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT` 必须固定为新 Issuer 下 `/protocol/openid-connect/auth`，不能使用当前 `auth-test` / 生产地址；需现场验证回调、SPA 登录与后端关联，静态设计不代表已可运行。
- 两个客户端都禁用 implicit flow、密码授权、service account、full-scope、web-origin 扩展，要求 consent；只准备**客户端结构提案**，不写入 Realm、没有真实注册操作、Keycloak 配置文件、私钥或密码。
- 合成账号占位仅为 `synthetic-owner-A` 与 `synthetic-owner-B`；真实 user ID **NOT_ALLOCATED**、`matrix-prp.mcp.expanded-user-ids` **NOT_CONFIGURED**、owner Client Grant **NOT_GRANTED**。安全边界来自 `McpScopeGuard.require()`：此名单默认为空且额外要求精确 ChatGPT Client ID；必须在获批的新环境独立造数后获取准确 ID，仅纳入获批的合成 owner，不许复制原 V2/生产 owner ID。
- `review_package(resource, issuer)` 明确标记 `deployable=false`、`not_a_keycloak_import=true`、`not_a_release_receipt=true`；`validate_proposals` 保持精确客户端定义，不容许变更回调、JWKS、aud、Scope 或禁用安全开关。新增单元测试仅使用虚构测试域名，不联网、不写磁盘、不生成/使用身份材料。

来源：2026-11-22 核对公开 `https://chatgpt.com/oauth/client.json` 中的 Client ID、唯一回调、`private_key_jwt`/RS256 与 JWKS URL；这是对**公开协议元数据的核对**，不代表真实 ChatGPT 登录或 Keycloak 注册成功。

**真实实施依旧 NO-GO：** 尚无已核实的独立主机、DNS/TLS/回调路由、可运行 Realm、授权的双 owner 数据、独立 G0/B2 恢复/回滚批准及真实 ChatGPT `Connect` 验收。即使本候选通过 CI，也**不得**安装 Client、创建账号、设置白名单、发放 Grant、改变生产或 V2，更不得合并 main。需要在具体目标确认后取得独立、明确的有状态变更审批。


## 12. 独立目标实施交接单（仍仅审查，不可安装）

新增加 [MCP218 独立目标实施包交接单](./mcp218-independent-target-implementation-review-20261122.md)，将原先分散在本方案的要求合并为**专属资源/容器与卷、MCP Resource、Issuer、SPA、精确 Client、合成 Owner、G0/B2 恢复、逐步启用及失败回滚**的责任和脱敏证据矩阵。

**该文件不是部署工件或审批收据**，没有 Compose、Ingress、Realm import、密钥、运行参数或真实主机分配；不能用老的 `prp-mcp` Runner 通过结果取代新的 `prp-mcp218` 目标实测。新文档中的全部资源、DNS/TLS、真实恢复及正式 Client 仍为 **UNASSIGNED / NO-GO**；在目标负责人提供可核查证据且完成单独审批前，不生成、安装或执行实际环境配置。

最新隔离浏览器/完整组合源码测试证据以 [#353](https://github.com/micor-cjj-spec/matrix-prp/pull/353) 的**确切 HEAD** `60ccba8d9115deecc9fa0b3f5c1a82569b4dfb9e` 为准：其 Push [7/7](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45055881360) 和 PR [6/6](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45055886640) 成功，证明合成签名 Keycloak / Chromium 第一方授权与撤销，不证明真实 ChatGPT Connect、目标部署/恢复或主线合并。
