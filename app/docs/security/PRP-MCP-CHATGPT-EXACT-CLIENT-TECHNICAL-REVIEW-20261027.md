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
