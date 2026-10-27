# ChatGPT → PRP 只读 MCP：首次身份绑定与最小公网路由评审（2026-10-27）

> **结论：P0 ACCOUNT BOOTSTRAP NOT IMPLEMENTED. NO-GO for real ChatGPT task reads.**
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
