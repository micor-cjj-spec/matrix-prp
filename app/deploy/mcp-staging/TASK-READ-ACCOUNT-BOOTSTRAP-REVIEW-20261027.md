# ChatGPT → PRP 只读 MCP：首次身份绑定与最小公网路由评审（2026-10-27）

> **结论：P0 ACCOUNT BOOTSTRAP CODE CANDIDATE; ISOLATED END-TO-END UNVERIFIED. NO-GO for real ChatGPT task reads.**
> 本文及 `render_readonly_link_routes` 仅为评审候选；无发布许可、不改动 Nginx/Keycloak/PRP、不开放 B2、不发放收据、不代表真实 ChatGPT OAuth 登录或 `prp_tasks_list` 已成功。

## 真实调用链的确认

PRP 当前在 `McpOAuthResourceServerConfig.mcpOAuthFilterChain` 中，接受签名有效、`iss`、时间、`aud` 验证通过的 OAuth JWT **之后**，还必须：

1. 通过 `McpIdentityLinkService.resolveUserId(iss, sub)` 查到此前已登记的 PRP 用户；未登记立即认证失败，MCP 不会继续执行。
2. 用户仍处于启用状态；通过 `McpClientGrantService.grantedScopes(owner, verified_client_id)` 校验用户的授权（每次请求查询，撤销下次即生效）。
3. 只将实际 JWT Scope 与已批准的 PRP Scope 交集映射为工具权限；`prp_tasks_list` 还有每次读取最多 20 条的业务限制。

PRP 首次身份绑定的**现有**另一路径：

- 用户登录 PRP `/prp/me/mcp-clients`，使用 PRP 会话 JWT + 重新输入密码，先 POST `/api/mcp/clients` 批准 `https://chatgpt.com/oauth/client.json` 的 `prp.tasks.read`；
- 再 POST `/api/mcp/identity/tickets` 获取一次性高熵关联码（10 分钟，仅保存 Hash）；
- **必须**由持有已验证的外部 Keycloak OAuth Access Token 的客户端，向 `POST /api/mcp/link` 提交关联码；此端点单独使用 OAuth JWT SecurityFilterChain，且 `McpIdentityLinkService.complete` 以签名中的 issuer、subject、client ID 核实票据；
- 关联成功后 `prp_tasks_list` 才会被正常授权。

**P0 冷启动死锁：** 当前 MCP `prp_tasks_list` / `tools/call` 在无身份绑定时返回 401；`McpToolConfiguration` 固定工具清单中**没有**关联账号工具；ChatGPT 的标准“关联”步骤尚无经验证的方式使其在取得签名 Token 后自动请求这个**额外** `POST /api/mcp/link`。前端页面也只是显示关联码，没有可执行该 OAuth Bearer 调用的步骤。

因此：**CI 成功证明 Keycloak 能签发正确的 Token，不能替代首次账号绑定。** 不应让用户把 PRP 密码、一次性关联码或 OAuth Access Token 发到普通 ChatGPT 对话，也不应要求使用浏览器开发者工具导出 Token。

## 候选解决路径与取舍（必须二选一后另行开发和验收）

**推荐 A：PRP 内完成独立的第一方 PKCE 身份绑定，ChatGPT 仅负责事后任务读取。**

1. 在 PRP 已登录的安全页面上，由用户核对**精确 ChatGPT Client ID**、只授予 `prp.tasks.read`，重新认证 PRP 密码，启动独立的第一方 OAuth 授权码 + PKCE S256 流程。
2. 一次性、短时、与 PRP 用户会话和目标 Client ID 绑定的 `state`、PKCE Verifier 和 OIDC `nonce` 存于服务器端；回调仅回到新批准的**第一方**固定 URI，回调必须验证 `state`、`iss`、ID Token 签名、`aud`、`nonce`、有效期及准确重定向。不得将 Access Token 发给浏览器或 AI。
3. 只从 Keycloak 签名的 `(iss,sub)` 创建映射；在同一 Realm 的不同客户端下，**必须单独核实该用户的 subject 是否一致**（尤其存在 pairwise-subject 配置时）。第一方临时客户端的 ID 不得伪装成 ChatGPT，也不能把第一方客户端的授权 Scope 当成 ChatGPT 授权。
4. 绑定写入是有意、经用户直接认证授权的 PRP 账户配置操作（不是 MCP 数据写入工具），必须一次性事务、抗 CSRF、阻止一对多/多对一冲突、可撤销并记安全审计事件。
5. 在真实 ChatGPT 完成 OAuth 后，用其**真正签发的** `(iss,sub,azp)` 与先前绑定匹配，另行验证客户端授权及 `prp.tasks.read`。仅这一步成功后才认定可读任务。

**备选 B：显式受限 MCP 冷启动绑定工具。** 必须创建特殊的 bootstrap 身份和独立的 token/call policy，使未绑定 OAuth JWT 只能调用单一绑定工具，所有其他工具（包括 tools/list 的暴露、TaskService、Finance、Drafts）在未绑定时拒绝；不得直接放宽现有 `McpToolConfiguration` 的 `UserProfile` 检查或把未绑定 token 视作 PRP owner。还须证实 ChatGPT 可以安全地执行该工具及消费关联码，且 UX 不诱导用户把票据贴入普通聊天。安全审查复杂度更高。

两条路径均尚未实施；**不允许**把仅增加一个公网 Nginx 转发路径视为完成绑定功能。

## 新增最小路由评审候选

`app/deploy/mcp-staging/approval_routes_pending.py` 新增了
`READONLY_LINK_EXACT`、`READONLY_LINK_REGEX`、
`render_readonly_link_routes(trusted_ca, port=18443)`。

候选仅列出以下 **10 个精确地址**：

| 路由 | 方法 | 实际用途 |
|---|---|---|
| `/prp/login`, `/prp/me/mcp-clients` | GET | PRP 登录与 MCP 客户端管理页 |
| `/api/auth/login` | POST | PRP 第一方登录 |
| `/api/users/me` | GET | 验证 PRP 会话账户 |
| `/api/mcp/clients` | GET, POST | 查看/显式批准客户端授权 |
| `/api/mcp/clients/revoke` | POST | 立即撤销 |
| `/api/mcp/identity` | GET | 查看已绑定外部身份 |
| `/api/mcp/identity/tickets` | POST | 重新认证、生成一次性票据 |
| `/api/mcp/identity/unlink` | POST | 重新认证、解除映射 |
| `/api/mcp/link` | POST | 已验证 OAuth Bearer 的原有绑定端点（**不能由此推断 ChatGPT 能调用**） |

另允许一个受约束的 `/prp/assets/<静态文件名>` GET 正则，用于前端静态资源；**本候选不能自行证明页面所需的全部动态分包/重定向均可访问**。现有页面有 `/me` 返回链接，点击会导航到尚未包含在此窄范围内的路径；此限制在完整浏览器验收前必须明确。

原较宽的 `render_approval_routes` 保留原状。新候选**不包含**：

- `/api/mcp/approval/drafts/<uuid>`、`/prp/me/mcp-approve/<uuid>` 或其他草稿/写入审批路由；
- 通用 `/api/**`、`/prp/**`、注册/管理员、财务或任务业务 API；
- 未经单独审核的第一方 OAuth 回调 URI（路径尚未实现）。

生成的代理仍要求 `$prp_stage_origin_ok`、固定回环 HTTPS upstream、证书验证和 SNI、方法限制、禁止缓存、禁用访问日志，**不能凭此单文件证明外层 Host/SNI/raw-URI/IPv6/HTTP2 守卫已安装**。

## 必须补齐的阻断验收

- [ ] 选择 A 或 B，形成完整代码实现和威胁模型；无账户绑定前，任何数据读取保持 401。
- [ ] 第一方 PRP 账号密码与外部 Keycloak 账号使用**完全分离**的会话，严格验证 `state/nonce/PKCE` 及 callback；如走 B，严格最小 bootstrap capability。
- [ ] 真实浏览器前端构建和动态资源清单核验，证明页面在仅限的路由表内能工作；当前只是**待评审**的候选。
- [ ] 真实 Keycloak 身份映射与 ChatGPT 真实授权 `iss,sub,azp` 一致；验证 Scope 是 `prp.tasks.read` 且无额外数据权限。
- [ ] 撤销客户端授权、解除绑定及过期/重放/错误票据均立即阻断 MCP 请求；跨用户不能读取任务。
- [ ] 原 V2 Nginx raw URI 独立审批、真实六文件安装/回滚凭证、新鲜 B2 独立恢复审核和客户端策略变更单均已由授权负责人完成。
- [ ] 最后由用户在 ChatGPT 界面实际执行 `prp_tasks_list`（最多 20 条），而不是仅看隔离 Keycloak OAuth CI。

**Gate:** `P0_LINK_BOOTSTRAP=BLOCKED`, `B2=NO-GO`, `LIVE_CHATGPT_TASKS=UNVERIFIED`; PR #113 继续 Draft。严禁创建假的 `approved-install.safe.json`、`fresh-b2-restore.safe.json` 或绕过受控发布。

## 2026-10-27: PR #113 中的第一方 PKCE 实现候选（默认关闭）

**源代码已实现、尚未部署；一次性 Keycloak + PRP MySQL + Java HTTPS 接口的浏览器形态 OAuth 联调已经通过，但真实浏览器前端、正式 Keycloak Client 与 ChatGPT OAuth 均未验收。** 本文开头的 `P0 ACCOUNT BOOTSTRAP NOT IMPLEMENTED` 为较早审查时刻的结论，现在应解读为 **`P0_ACCOUNT_BOOTSTRAP=CODE_READY_REQUIRES_ISOLATED_E2E`**；它仍不意味着 ChatGPT 可以读任务。

提交到测试分支的代码包括：

- `V28__mcp_first_party_oidc_link_flows.sql`：5 分钟、一次性 `state_hash`、`code_verifier` 和 `oidc_nonce` 数据库记录。Keycloak 用户密码和 OAuth Access Token 不持久化。
- `McpFirstPartyOidcLinkService`：只有原 PRP 登录 JWT + 再次校验密码 + 已批准 ChatGPT `prp.tasks.read` 才能启动；只对固定第一方客户端执行 `openid` 授权码 + S256，回调核对 state 和 Issuer，状态先消费后换码，ID Token 只在后端验签，固定 OIDC Audience 与 nonce 检查；成功后调用事务式一对一映射。
- `McpFirstPartyOidcLinkController`：`POST /api/mcp/identity/oidc/start`、`POST /api/mcp/identity/oidc/finish`。两个端点均走**原 PRP 会话 JWT**，不是外部 OAuth JWT，默认不存在。
- `McpIdentityLinkService.linkFirstPartyOwner`：复用现有映射表、一对一唯一约束及授权撤销防护；发生碰撞或撤销必须拒绝。
- `McpClientsView.vue` 和 `McpOidcCallbackView.vue`：PRP 绑定按钮从固定测试 Issuer 启动、严格审核返回地址；回调页面同步清除 URL 查询参数后才发认证请求，绝不向 ChatGPT 发送 code、state、Token 或 PRP 密码。
- `approval_routes_pending.py`：在原审查候选基础上，**独立的**只读绑定候选添加 3 个严格路由（`GET /prp/me/mcp-link/callback`，两个 `POST /api/mcp/identity/oidc/*`）。因此当前该候选是 **13 个 exact paths + 1 个 static asset regex**，不包含草稿写入审批、通用 API 或动态 Keycloak 管理接口。

启动前配置（**示意，不要将其应用到活跃容器**）：

```properties
matrix-prp.mcp.enabled=true
matrix-prp.mcp.oauth.enabled=true
matrix-prp.mcp.oauth.first-party-link.enabled=true
matrix-prp.mcp.oauth.first-party-link.client-id=prp-first-party-link
matrix-prp.mcp.oauth.first-party-link.redirect-uri=https://prp-test.micor.top/prp/me/mcp-link/callback
```

依赖已有固定 issuer `https://auth-test.micor.top/realms/prp-mcp`、固定 JWKS `.../protocol/openid-connect/certs` 以及资源 `https://prp-test.micor.top/api/mcp`。前端浏览器重定向**固定**到该测试 Issuer，错误的主机/路径拒绝。独立 Keycloak client `prp-first-party-link` 必须是 public、Authorization Code enabled、PKCE **S256 required**、精确上述回调、`openid`，不能开启 Password/Implicit/Service Account，不得冒充 ChatGPT；这项客户端注册在当前线上未执行。

### 不能因编译成功而宣称完成的 P0

1. 必须在隔离 MySQL + 真 Keycloak 的同一端到端会话下运行真实 PRP `/start`、浏览器登录/回调 `/finish`，验证**真实签名的 ID Token**、Nonce、State、Audience，以及错误密码、错误回调、多次提交、切换 PRP 用户、同一 Keycloak 身份绑定第二个 PRP 用户、已授权后撤销这些负例。当前 Mockito/unit CI 不等于 E2E。
2. 以真实测试 Realm 比较第一方客户端和**单独** ChatGPT 客户端签发的同一登录用户的 `sub`。若 Keycloak 配置 pairwise subject 或其它 subject 转换，拒绝直接复用映射；必须设计由管理员审核的跨 client subject 映射，不能猜测。
3. 回调及前端资源必须经独立变更批准、实际浏览器 HTTPS/SNI/Referrer-Policy/Host 测试；任何 302、跨站资源加载、日志记录若泄露 `code` 或 `state`，都是阻断项。
4. 最终 PRP 绑定后仍需真实 ChatGPT OAuth `private_key_jwt`、刷新和 `prp_tasks_list` 验收。B2 两份独立安全凭证缺失，原控制器不可跳过。

**发布状态：`feature.default=OFF`，`PR#113=Draft`，`B2=NO-GO`。** 任何配置属性的示意值不是变更授权。

## 2026-10-27 05:46 UTC — 真实一次性服务 E2E 证据（不包含真实 ChatGPT）

**GitHub Actions:** [40456981066](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40456981066)，独立新 job `PRP first-party OIDC linking real disposable E2E` **SUCCESS**。第一个无解绑增强版的完整通过记录为 [40456652028](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40456652028)。

CI 使用全新 MySQL 8.4、Keycloak 26.8.0、PRP Java 21 后端和 CI 自签 CA 的 HTTPS Nginx，运行真实的 OAuth Authorization Code + S256 token 交换及 PRP V28 MySQL 事务。**浏览器形态驱动器是 Python HTTP+CookieJar+Keycloak 登录表单驱动，不是 Chrome / Safari 图形浏览器。**

**E2E 验收取得的具体证据：**

1. 未绑定的外部 OAuth bearer 调用 MCP 返回 401；PRP Owner 可以只为任务查询批准一个合成 OAuth MCP 客户端，且同时单独授权标识为 `https://chatgpt.com/oauth/client.json` 的客户端 grant（**此步骤没有真实 ChatGPT Token**）。
2. 只有 PRP 密码正确且上述 grant 存在时才允许 `POST /api/mcp/identity/oidc/start`；它产生服务器端的一次性状态及 PKCE verifier，CI 驱动器**拿不到 verifier**。
3. 使用另一独立、专门为此次 E2E 新建的公共 S256 客户端 `prp-first-party-link`，真实 Keycloak 登录和回调后执行 PRP `/finish`；PRP 在后端交换 code、验证实际签名的 ID Token 后写入持久 MySQL 映射。
4. 从 PRP 用户身份接口取回 `(issuer,subject)`，与**单独合成的** MCP 测试客户端 `prp-pkce-probe` 的已验签 Access Token `(issuer,sub)` 比较，**在该一次性 Realm 中一致**。这**不意味着生产 Keycloak 的 pairwise `sub` 已验证，也不证明真正的 ChatGPT Client ID 签发 `sub` 一定相同**。
5. 账号绑定后 `initialize`、`tools/list`、`prp_tasks_list` 成功，财务工具因没有其授权被拒绝。
6. 错误 PRP 密码、错误返回 Issuer、重复消费 `state` 被拒绝。**新增强的真实数据库场景：**解绑后尚未完成的 State 被拒绝（409），映射表不再返回该用户关联记录，原先有效的签名 MCP bearer 再次调用即返回 401。
7. 撤销合成客户端的 grant 后，独立 MCP 测试请求也返回 401。CI 所有数据库、证书、账户和容器随 Runner 结束销毁。

**审核边界与尚存 P0：** 这不验证 iPhone/Safari 或真正的浏览器 SPA 页面工作；不验证 OpenAI 私钥的 `private_key_jwt` 或真实 ChatGPT 两步授权后 `sub`；不证明正式公网独立 vhost、页面静态资源、回调路由、B2 控制器、生产恢复链路已放行。Keycloak 原生 CIMD 元数据字段兼容问题仍未消失；继续采用精确预注册候选审查路线而非假称已安装。生产配置未变、PR #113 保持 Draft、B2 保持 NO-GO，MCP 写入关闭。

**阶段结论：** `P0_ACCOUNT_BOOTSTRAP=DISPOSABLE_E2E_PASSED`，`LIVE_CHATGPT_TASKS=UNVERIFIED`，`B2=NO-GO`。

## 2026-10-27 06:20 UTC — 真正 Chromium/Vue 浏览器 E2E 已通过

**证据：** [GitHub Actions 40459821556](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40459821556) — job `Actual Vue/Chromium login and callback with isolated Keycloak/MySQL` **SUCCESS**，对应提交 `7c841c173d36552f75956266cd1fbcc25b4aaf5d`。

CI 先用 `VITE_APP_BASE=/prp/` 构建真实 Vue 页面，通过一次性 HTTPS Nginx 只读提供 `/prp/` 静态资源；Playwright 的**实际 headless Chromium** 在隔离的 MySQL 8.4、Keycloak 26.8.0 和 PRP Java 21 环境中完成：

1. 以预设的一次性 PRP Owner 会话打开 MCP 客户端管理页面并点击 Keycloak 身份绑定按钮；浏览器请求 `/start`、按**构建时固定的授权端点**跳至 Keycloak。
2. 实际浏览器填写一次性 Keycloak 用户账号密码，并经过其授权页面；Keycloak 向 PRP 回调页面提供授权结果。
3. Vue 回调页面成功调用 PRP `/finish`，后端使用数据库 PKCE verifier 向真实 Keycloak 交换授权码并验证签名 ID Token；回调成功，**浏览器 URL 的 code/state 查询参数已清除**。
4. 页面发出的请求只涉及一次性 PRP / Keycloak 两个 origin；CI 驱动在浏览器侧拒绝额外第三方网络目标。
5. 已保存 Keycloak `iss/sub` 与独立合成 MCP bearer `sub` 一致；外部 synthetic MCP bearer 的 `prp_tasks_list` 可读，Finance 工具无权访问；解绑立即阻断 MCP 和未完成 PKCE state。

**安全边界：** CI Chromium 为了接收一次性自签证书启用 `ignore_https_errors`；Python 及后端真实 E2E 单独验证 TLS CA。不能把浏览器自签证书例外用于正式环境。为处理浏览器同源 API 的 HTTP 403，CI 仅在**固定回环 HTTPS 代理**环境启用 Spring `SERVER_FORWARD_HEADERS_STRATEGY=framework`，未扩张 CORS 白名单；生产需独立评审边界代理与 forwarded-header 信任。

这里的浏览器是真正 Chromium，不是 Safari/iPhone；测试使用**独立合成 MCP 客户端** `prp-pkce-probe`，而非真实 ChatGPT 私钥、Token 或 Session。公网测试 Keycloak/真实 ChatGPT 签发主体一致性仍需核验；生产静态资源、raw-URI Host/SNI/IPv6/HTTP2 守卫和 B2 签署凭证仍缺失。

**新增独立边界测试（与上述成功 CI 分开判定）：** 当回调时 PRP 会话过期，不能把 `code/state` 转发给 `/login?redirect=...`。相应安全守卫和浏览器负例已在测试分支提交；**必须等最新负例 CI 完成后才能将其标为通过**。

**阶段状态：** `FIRST_PARTY_CHROMIUM_DISPOSABLE_E2E=PASSED`；`EXPIRED_SESSION_CALLBACK_NEGATIVE=UNVERIFIED_UNTIL_CI`；`LIVE_CHATGPT_TASKS=UNVERIFIED`；`B2=NO-GO`。

## 2026-10-27 06:27 UTC — OAuth callback 失效会话泄露负面测试

新增了 `app/web/src/utils/oidcCallbackPath.ts` 的**精确回调路径识别**：当 PRP 主动检查当前用户遇到 401 时，`main.ts` 不会将尚含 `code/state` 的 Keycloak 回调 `fullPath` 复制进 `/login?redirect=...`；回调 Vue 本身继续在异步操作前清除原地址栏的查询参数并显示登录过期/绑定失败。

- [GitHub Actions 40461031062](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40461031062)：离线 OAuth 契约、后端 Java、前端 Vue 类型检查及**精确回调路径单元测试 PASS**。
- [GitHub Actions 40460981578](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40460981578)：真正 Vue + Chromium + 一次性 Keycloak/MySQL/Java **SUCCESS**；在已经成功的 PRP 页面绑定之上，Playwright 额外以**无 PRP Session**和**过期/无效 PRP Session**分别加载带人工占位 `code/state` 的回调页面，断言 URL 被清理、保持精确回调路径且没有把 `code/state` 传入 `/login` 导航。测试中的 `code/state` 全为 synthetic，不是 OpenAI 凭证。
- Chromium 日志再次确认真正 Vue 页面、固定 Keycloak 登录、服务器端 PKCE 回调、映射和 task-read 通过；解绑后 pending state 和旧 bearer 拒绝。

**当前可关闭的隔离测试验收：** `FIRST_PARTY_CHROMIUM_DISPOSABLE_E2E=PASSED`，`EXPIRED_SESSION_CALLBACK_NEGATIVE=PASSED`。

**仍未验证的线上发布前条件：** iPhone Safari 真机表现、线上首方 Client/ChatGPT Client 的签名 `sub` 一致性、OpenAI 真实 `private_key_jwt`、受控外部 Nginx Host/SNI/raw-URI/IPv6/HTTP2 验收、B2 独立审批和恢复双凭证。生产环境保持不变，`LIVE_CHATGPT_TASKS=UNVERIFIED`、`B2=NO-GO`。

## 2026-10-27 07:20 UTC — 真实 MySQL 并发 PKCE 配额漏洞与修复

**发现：** 在一次性 MySQL 8.4、Keycloak 26.8.0、PRP Java 21、HTTPS 代理的真实测试环境，六个并行 `POST /api/mcp/identity/oidc/start` 均返回 HTTP 200；经只返回聚合数值的数据库查询证实，`prp_mcp_oidc_link_flows` 至少有 **6 条仍有效的 pending state**（总 8 条中此前两条已消费）。日志 `CONCURRENT_PKCE_CAP_FAILED_HTTP_200x6_DB_TOTAL_ACTIVE_MIN_MAX_8_6_299_300` 来自 [失败 CI 40465768608](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40465768608)。这是真实配额缺陷，不能把旧的 3 流程限制测试当作通过。

**原因：** `McpFirstPartyOidcLinkService.begin` 在 `@Transactional` 开始后先执行 consent、owner 等普通读，InnoDB `REPEATABLE READ` 的一致性快照可能在取得 `prp_users FOR UPDATE` 排它行锁**之前**建立；之后普通 `SELECT COUNT(*)` 继续使用过期快照，六个串行持锁事务仍可能各自读取到旧的零条状态。

**修复：** 保留用户行锁，并把三流程配额检查改为 `SELECT state_hash ... LIMIT 3 FOR UPDATE` **锁定当前读**；读已提交的最新 pending 状态，触及 3 条立即 429，不使用旧快照的非锁定 COUNT。新增六并发真实 MySQL 验收；[修复版 E2E CI 40465988250](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40465988250) **SUCCESS**，以及 [Java/前端/OAuth 契约 CI 40466095499](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40466095499) **SUCCESS**。CI 测试身份、数据库均随 Runner 销毁，没有访问活跃数据库。

**秘密最小化：** 完成 `/finish` 时在一次性状态消费 SQL 中同时清空 `code_verifier` 和 `oidc_nonce`；主动 `/unlink` 时清空未完成状态的这两个字段；合法用户下一次发起绑定前，清空已过期记录的临时秘密，并删除该用户名下一天以前的陈旧记录。**注意**：机会式按用户清理不保证长时间不登录的旧账号记录会立即清理完毕，正式运行仍需单独设计受控的周期性垃圾回收及可审计的保留期。

**发布边界不变：** 这是修复一个真实并发漏洞和数据最小化缺口，**不是**额外的 Nginx、Keycloak、B2 安装审批或真实 ChatGPT OAuth 验收。PR #113 保持 Draft；原安全控制器及 13 个活跃客户端没有在本轮修改。ChatGPT `prp_tasks_list` 真实连接仍未得到验证。
