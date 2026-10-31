# PRP MCP × ChatGPT 精确预注册 OAuth 客户端：独立技术评审（2026-10-27）

**评审性质：** 代码与公开规范的只读技术审查；**不是**授权操作人签署的 Nginx 安装许可、Keycloak 变更单、生产批准、B2 恢复凭证或安全合规证明。

**结论：有条件可行，P0 阻断未解除，NO-GO for live Realm deployment.** 允许继续在一次性 Keycloak/隔离恢复克隆中验证；不得改动原始安全门禁、给现有 13 个客户端施加额外策略或激活 PRP 写入。

## 评审依据

- `app/deploy/mcp-oauth/ci_chatgpt_cimd_pkce.py`：真正用官方 ChatGPT ID 做过授权入口 PKCE 测试；无真实 token。
- `app/deploy/mcp-oauth/ci_jwt_authcode_refresh.py`：**另一个测试客户端**跑通签名 JWT + 真实授权码、资源约束、刷新及吊销，不能替代 ChatGPT 客户端本身的 token 验收。
- `app/backend/src/main/java/com/matrix/prp/mcp/McpOAuthResourceServerConfig.java`：验证签名、issuer、时间、精确 `aud`、客户端授权和 PRP owner 映射。
- `app/deploy/mcp-oauth/chatgpt-cimd-repair.md`、`app/deploy/mcp-oauth/keycloak-resource-guard/B2-RELEASE-GATE.md`、`V2-RAW-URI-INDEPENDENT-CHANGE-REVIEW-20261027.md`：变更历史、安全门禁和恢复要求。
- Keycloak 26.8.0/26.8.1 一次性容器 CI：https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40446785882
- OpenAI 规范：https://developers.openai.com/plugins/build/auth
- Keycloak 官方文档：https://www.keycloak.org/securing-apps/mcp-authz-server
- Keycloak PKCE CIMD Issue #52795：https://github.com/keycloak/keycloak/issues/52795

## 已取得且可以引用的证据

1. 两版 Keycloak 的**原生** `client-id-metadata-document` 对 ChatGPT 的 `token_endpoint_auth_methods_supported` 字段解析失败，不能称为已可用。
2. 一次性 Realm 中精确预注册 `https://chatgpt.com/oauth/client.json`、精确回调 `https://chatgpt.com/connector_platform_oauth_redirect`、官方 JWKS URL 后，S256 和 `openid offline_access prp.tasks.read` 的授权端入口返回被测试器认为可接受的响应；漏传 challenge 或选择 `plain` 均被拒绝。
3. Admin REST 回读 `publicClient=false`、`fullScopeAllowed=false`、S256、精确 callback，Optional Scopes 只有 `prp.tasks.read` 与 `offline_access`。
4. 外部公网已实测 PRM 200、未授权 initialize POST 401 与 Bearer Challenge，Keycloak discovery/JWKS 可达；真实 ChatGPT OAuth 及 tool call **未验证**。
5. 当前 B2 发放所需的 `approved-install.safe.json` 和 `fresh-b2-restore.safe.json` **均缺失**，且缺失不是可以人工填充或模仿的技术数据。

## P0：独立发布阻断项（尚未通过）

| ID | 问题和已发现的证据缺口 | 必须验收 |
|---|---|---|
| P0-1 | 精确预注册分支没有真实 `authorization_code` → `private_key_jwt` token 交换。另一个合成客户端的 E2E 不可迁移为本客户端的证据 | 以**同一客户端配置**（但隔离测试公私钥和严格受控 JWKS）完成 code + PKCE + assertion 验证，负例覆盖错误签名、错误 `aud`、错误 `iss/sub`、过期、重放、回调不匹配；实际 OpenAI 客户端仍需真实授权完成最终验收 |
| P0-2 | 预注册 `protocolMappers` 当前使用 `included.client.audience=matrix-prp-mcp-resource`，而 PRP 后端要求精确 HTTPS Resource `https://prp-test.micor.top/api/mcp`。Keycloak resource-indicators 可能补充或替代 Audience，但本客户端**无已验证 Access Token** | 使用同一已注册客户端签发并验签 JWT，确认 `aud` 精确包含指定 URI；若需自定义 Audience Mapper，应独立复核 `included.custom.audience` 与 Keycloak Resource Indicators 的叠加行为及最小权限 |
| P0-3 | 刷新令牌错误 `resource`、省略 `resource`、重复键、错误 Scope、旋转及撤销仅由另一合成客户端和独立 SPI 验证 | 审核对精确客户端生效的政策关联条件，在**同一客户端**验收错误资源/Finance/Write Scope 拒绝、refresh rotation、replay/revocation；实际 ChatGPT refresh 请求参数也要验证 |
| P0-4 | 稳定 `client_id`/callback 是条件性协议配置，现有测试未核实发布的 `authorization_response_iss_parameter_supported` 与**真实授权成功和错误重定向**的精确 `iss`；账户管理页所选回调模式也未核实 | 以 ChatGPT 管理页显示值为准：验证当前实际客户端 ID、准确回调、RFC 9207 `iss` 支持和全部授权结果；不臆测稳定模式 |
| P0-5 | 后端读取任务要求 PRP Owner 另行批准客户端并完成 OAuth subject 绑定；现有 review-only Nginx allowlist 不一定包含用户授予/绑定页面及 `/api/mcp/link` | 独立审批最小浏览器 / pairing 路由，通过真实 PRP owner 授权与绑定，验证本人最多 20 条、他人拒绝、撤销立即拒绝；不能擅自开放 `/api/**` |
| P0-6 | Nginx 原始控制器的旧候选与新的 V2 raw-URI SHA 源序不同，实际六配置文件放行凭证不成立，B2 两份独立审批凭证缺失 | 进行 G0 独立差异和真实安装授权、外部 IPv4/IPv6/TLS/HTTP2 验收、受控回滚、独立 <=3600 秒恢复签名证据；保留全部原始控制器和 13-client 状态；批准前只做只读/隔离操作 |

## P1：可观察性及回归强度

1. `require_pkce_result("S256")` 当前接受普通 HTTP 200，或到 Realm 内部路径的 302，而**不检查这确实是登录表单**。因此既有 CI 输出“reaches login entry”应严格表述为“授权请求达到可接受状态码”；加入页面结构识别（不打印 HTML / state / code）和错误页拒绝断言。
2. 可选 Scope 集合虽回读准确，但没有验证默认 Scope、Realm 默认值和**最后签发的 Scope**；必须验证不会出现 `prp.finance.read`、`prp.wellness.read` 或任何 `prp.write.*`。
3. `clientAuthenticatorType=client-jwt` 与 `use.jwks.url=true` 尚无此客户端的实际 JWKS 抓取、`kid` 密钥轮换和错误算法拒绝证据；需直接验证而非推断 26.8 支持。
4. 需要对原有 13 个客户端/Policies/Profiles/Mappers 进行变更前后**结构化比较**，确保精确预注册方案不会通过 Realm-wide Policy 放大其他客户端权限。
5. 当前测试把被拒绝/超时按明确分类区分；继续保持“网络超时 = UNVERIFIED”，不得当成正确的 401/421。

## 推荐路线与安全边界

**推荐采用“精确预注册”作为下一轮隔离验证方案，不采用当前无法解析官方 ChatGPT 文档的原生 CIMD 配置直接进入正式安装。** 这个推荐仅是技术路线选择；Keycloak 官方还描述了自定义 Executor 归一化 CIMD 字段的路径，也必须受独立兼容性和安全评审约束。

验收顺序：

1. 在 disposable Keycloak 把 `ci_chatgpt_cimd_pkce.py` 的预注册配置单独提升成可回放的 **测试用客户端配置**，先消除 P0-2 Audience 不确定性并加强 200 登录页识别。
2. 对**同一个**测试客户端进行完整授权码/PKCE/签名 JWT/Refresh/Scope/Audience 负面矩阵。测试密钥仅留在 CI；不接触 OpenAI 私钥、真实用户令牌或活跃 Realm。
3. 在隔离恢复克隆上验证 13-client 前后等价、Profile/Policy 影响范围、可逆回滚及原始 G0-G4 门禁审查；将签署的变更批准和恢复实证单独留给授权操作人。
4. 只有在原始门禁真实放行与严格 scoped 公网路由批准后，才能进行 live Realm 小范围变更，再由用户从 ChatGPT UI 真正完成 OAuth 登录、授权、PRP 绑定和 `prp_tasks_list` 只读验收。

## 评审裁定

- **技术方向：CONDITIONALLY VIABLE — 允许继续在一次性环境验证。**
- **当前精确客户端配置：P0 REVIEW REQUIRED。**
- **实时 Keycloak / Nginx 变更许可：NO。**
- **B2 release approval：NO-GO。**
- **PR #113：保留 Draft；不合并、不部署；MCP writes OFF。**

本文件是评审记录；不可作为 `approved-install.safe.json`、`fresh-b2-restore.safe.json`、管理员授权票据或 B2 cutover 证明。

## 2026-10-27 04:10 UTC — 实际授权码/Refresh 的 CI 新证据

**证据：** [GitHub Actions 40448153185](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40448153185)，Keycloak **26.8.0/26.8.1 双版本均 SUCCESS**，对应提交 `57f8ca691dfbd1bcd1a31befe02e95b18193944a`。

**已证实的技术修复：** 将精确预注册客户端的 Audience Mapper 从 `included.client.audience=matrix-prp-mcp-resource` 修正为 `included.custom.audience=RESOURCE`，并以同一个官方格式的 Client ID `https://chatgpt.com/oauth/client.json` 和回调 `https://chatgpt.com/connector_platform_oauth_redirect`，在短生命周期的一次性 Keycloak Realm 中完成：

- 临时用户的 Keycloak 登录、授权同意、授权码和 S256；错误 `code_verifier` 被拒绝。
- `private_key_jwt` 客户端认证、签名 Access Token 的 Issuer/Subject/Client ID 和精确 MCP HTTPS `aud` 验证；只含任务读取权限，不授予财务/健康/写入权限。
- `openid offline_access prp.tasks.read` 的真实授权码换取，签发刷新令牌，错误客户端签名、错误/空/省略/重复 `resource`、财务 Scope 扩张均被拒绝。
- Refresh Token 轮换、旧 Token 重放和新 Token 吊销验证；单客户端绑定的 refresh-resource 防护 Policy 回滚后保持原状。
- 保留原 Client ID、Redirect URI、S256 和授权 Scope；完整流程使用真实 Keycloak 26.8 OAuth 端点而非模拟 HTTP 响应。

**不可忽略的真实性差异（仍属 P0）：** 官方 ChatGPT 的远程 JWKS 不可能为测试者生成的 JWT 签名，因此 CI 仅在**一次性 Realm**将该客户端的凭证校验源由 `https://chatgpt.com/oauth/jwks.json` 改成临时 X.509 测试公钥。客户端身份标识相同、凭证源不同。**这不验证任何 OpenAI 真实签名，也不证明实际 ChatGPT 会用同样参数执行授权/刷新。** 不得称为正式 OAuth 端到端成功。

**评审状态更新：** 原 P0-1（完整 Auth Code PKCE 令牌流程）和 P0-2（精确 URI Audience）已取得**隔离、测试凭证条件下**的通过证据；P0-3（Refresh 行为）在相同的临时客户端身份与精确资源策略下通过隔离负面测试。但需用真实 OpenAI 客户端断言、公网完整流程、真实 PRP 用户绑定和生产关联页完成独立验收。G0–G3/B2 没有因这些测试自动放行，原生动态 CIMD 解析阻塞也没有解除。

**更强的界限：** `ci_chatgpt_exact_client_authcode.py` 需要 GitHub Actions 隔离运行器、固定 loopback Keycloak 和临时 RSA 文件。脚本中的 Admin REST 客户端修改仅允许一次性 Realm；在没有原始批准和独立恢复签名的情况下，绝不复制这些调用用于线上 Keycloak，更不能把临时证书或合成刷新策略写入生产 Realm。

**总体裁定仍然：CONDITIONALLY VIABLE for further isolated validation / NO-GO for live deployment。**

## 2026-10-27 04:40 UTC — 冷启动身份绑定 P0 与最小只读路由候选

复核 `McpOAuthResourceServerConfig`、`McpToolConfiguration`、`McpIdentityLinkService`、`McpOAuthLinkController` 和 PRP 前端 `McpClientsView.vue` 后确认：

**即便真实 ChatGPT OAuth Access Token 成功，未绑定的 `iss,sub` 仍被拒绝执行 MCP 工具。** 目前前端只能生成 10 分钟的一次性绑定票据，现有完成接口 `POST /api/mcp/link` 必须由已验证 OAuth Bearer 调用；ChatGPT 标准 MCP 工具列表没有用户身份绑定工具，也没有已验证的客户端自动调用该 API 的工作流。此项不是 CI 的 Token 成功能够推断解决的。

独立新文档：`app/deploy/mcp-staging/TASK-READ-ACCOUNT-BOOTSTRAP-REVIEW-20261027.md`；列明优先的**第一方 PRP Keycloak PKCE 绑定流程**（与 ChatGPT OAuth 客户端分离）和备选最小权限冷启动工具，分别需要安全审查与新增实际实现。不得引导用户把票据、密码或 OAuth Token 发到普通聊天或浏览器开发者工具中。

已经新增的 `render_readonly_link_routes` 仅生成 **10 个精确页面/API 路径 + 1 个静态资源正则**，沿用固定回环 HTTPS、`proxy_ssl_verify on` 服务端证书校验与限定 SNI；**未声称启用双向 mTLS**。 不含任何草稿审批路径、通用 API 或未开发的回调路径；`render_approval_routes` 既有更宽候选保持不变。GitHub Actions 40451039140 的 route generator/合同测试 **10/10 通过**，但测试结果不意味着浏览器配对实现或新路由有安装许可。

**新 P0：ACCOUNT_BOOTSTRAP_BLOCKED。** 实际 Keycloak 配置/13 客户端恢复、B2 双凭证、受控路由变更、真实 ChatGPT 登录和 `prp_tasks_list` 均没有因新代码或该文档自动放行。PR #113 保持 Draft、NO-GO。

## 2026-10-27 — 首次身份绑定完成真实一次性服务 E2E（非 ChatGPT）

独立 CI：https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40456981066（SUCCESS）。

- 将 PRP `V28` 一次性 PKCE 流程、Keycloak 26.8.0、MySQL 8.4、Java 21 和 HTTPS Nginx 在同一全新隔离环境中真实启动；
- PRP 发起授权、模拟浏览器登录、真实签名 ID Token 验证及保存 `issuer,sub` 的 MySQL 操作已经跑通；
- `prp-first-party-link` 和另一个**合成** MCP Client `prp-pkce-probe` 登录同一 Keycloak 测试用户，签名 Subject 在该 Realm 中一致；已联通 `prp_tasks_list`，Finance 权限拒绝；
- 真实 MySQL 解绑使尚未用完的 State 失效，原已可用的 JWT 后续 MCP 请求 401；拒绝密码错误、Issuer 不符、State 重放和授权撤销。

**此项只关闭“隔离开发与受控 E2E 测试”范围内的 P0 代码验收缺口。** 还须验证真实 ChatGPT 预注册客户端的 `iss/sub/azp`、真实 OpenAI 凭证、第一方浏览器路由在 Safari/Chrome 中的实际安全表现，以及经审批的公网回调和 B2 控制器；不能用合成 Keycloak 客户端身份映射来冒充 ChatGPT 授权成功。Nginx/Keycloak 原有正式运行环境未修改，发布判定继续 **NO-GO**。

## 2026-10-27 — 完整 Vue/Chromium 浏览器与过期回调安全负例

已获得全新 disposable Chromium、Keycloak 26.8.0、MySQL 8.4、PRP Java 21 + Nginx 的真正浏览器端到端 SUCCESS 证据：
[40459821556](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40459821556)（正常账号绑定并调用任务）和 [40460981578](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40460981578)（进一步验证无 PRP 会话/会话过期时不会通过登录重定向泄露回调 `code/state`）。离线前端路径单元测试与 OAuth 契约亦在 [40461031062](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40461031062) 全通过。

该证据已进一步关闭首次绑定**隔离代码**的 Chromium E2E 风险，不能替代真实 ChatGPT 授权、官方 OpenAI 密钥断言、生产 Keycloak 的 `sub` 一致性、Safari/iOS 验证和受控 Nginx/B2 批准。正式 Keycloak、PRP 和 Nginx 未修改，PR #113 仍 Draft，**发布结论继续 NO-GO**。

## 2026-10-27 06:40 UTC — Official ChatGPT JWKS / RFC 9207 isolated evidence

**Keycloak 26.8.0 + 26.8.1 both passed:** [GitHub Actions 40462309500](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40462309500), commit `834b7e16d98e0f01b477271944d9181029a7bc98`.

Before replacing the official JWKS URL with an unrelated temporary CI certificate, the test now independently checks all of these conditions:

1. **Readback of exact ChatGPT pre-registered client:** `clientAuthenticatorType=client-jwt`, `use.jwks.url=true`, literal `jwks.url=https://chatgpt.com/oauth/jwks.json`, exact Client ID and redirect, `fullScopeAllowed=false`.
2. **OpenAI public JWKS network reachable:** a no-write Python container temporarily joins the disposable Keycloak container's **network namespace**, makes one certificate-validated HTTPS GET of the official public JWKS, ensures public RSA signing keys, and outputs only a bounded PASS code. It does **not** run within the Keycloak JVM or prove that the JVM's separate trust store/HTTP client completed an equivalent fetch.
3. **Negative signed client assertion:** a non-OpenAI, ephemeral RSA private key signs a `private_key_jwt` with official-format Client ID and an explicitly bogus `kid`. The *real* pre-registered Keycloak token endpoint returns OAuth `invalid_client`. This demonstrates rejection of this untrusted signature; it is **not** proof of successful verification of any real OpenAI signature.
4. **Real RFC 9207 error response:** a sessionless Authorization Code + S256 + `openid offline_access prp.tasks.read` request with `prompt=none` returns a redirect to the exact registered ChatGPT callback with `error=login_required`, unchanged `state`, and canonical Keycloak `iss`, without code, ID Token or Access Token. This checks one critical error response; it does **not** exhaustively prove `iss` on every possible OAuth error or real ChatGPT callback mode.
5. The pre-existing test then deliberately substitutes a temporary X.509 key in the disposable client to complete the separate full authorization-code, token audience, refresh, rotation, replay and revoke matrix. **The test key is not an OpenAI key, and the substitution is not a proposed live client configuration.**

**Updated finding:** `P0-4` has one verified RFC 9207 no-login error response, not every authorization/error mode. The public official JWKS egress prerequisite is verified at the **network namespace** level only. **Still missing:** actual Keycloak JVM fetching/verifying OpenAI-managed JWKS under live TLS trust, real OpenAI-signed client assertion, real ChatGPT callback, per-user account Subject in the live Realm, reviewed routes, and two independent B2 approval/restore receipts.

**Release decision unchanged:** `LIVE_OAUTH=UNVERIFIED`, `B2=NO-GO`; PR #113 remains Draft; no host/production Nginx or Keycloak writes.

## 2026-10-27 — 首方绑定安全复核与签署门禁待办

**隔离环境新证据：** [PRP Java/OAuth 契约 CI 40463600050](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40463600050) **4 jobs SUCCESS**；[真实一次性 Keycloak/MySQL/PRP E2E 40463540580](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40463540580) **SUCCESS**（该 E2E 执行了生产代码对应的提交，但在后来新增的单元测试提交之前）。这不包含真实 ChatGPT Token。

两项独立审查后的代码收敛：

1. `McpFirstPartyOidcLinkService.validFirstPartyIdTokenAudience` 除了验证第一方 OAuth Client ID 必须在 ID Token `aud` 中，还验证**一旦 `azp` 存在，必须与第一方 Client ID 一致**；多个 `aud` 时 `azp` 仍为强制。原代码在单一 `aud` 场景可能接受错误 `azp`。六项本地 token 数据结构的正反断言已进入 Java CI。
2. 一次性 PKCE 的五分钟 `expires_at` 使用 `DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 5 MINUTE)`，之后的过期检查继续由 **相同 MySQL 时钟**决定，不再受 Java 主机或数据库容器时区差异影响。真实 MySQL 8.4 E2E 保持通过。

**尚未得到的真实现场证据和独立授权没有减少：** 真实活跃 Realm 的 13 个旧客户端不变性、两个精确批准的新增 Client/Policy 配置、ChatGPT 官方签名客户端断言在 Keycloak JVM 内的有效验证、两个客户端签发同一用户 Subject 的一致性、公网 Nginx Host/SNI/IPv6/HTTP2 与回滚、新鲜 B2 恢复凭证、用户亲自完成 OAuth 的只读 `prp_tasks_list`。

**裁定：** PR #113 只作为 **Draft 安全验证候选**；严格维持 `B2=NO-GO` 与 `LIVE_CHATGPT_TASKS=UNVERIFIED`，禁止将上述 CI 输出自动转换成 `approved-install.safe.json`、`fresh-b2-restore.safe.json` 或生产安装许可。
