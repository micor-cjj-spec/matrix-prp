# MCP #218 独立目标实施包交接单（非安装工件）

> **REVIEW_ONLY / NOT_DEPLOYABLE / G0_B2_NO_GO / NO_AUTHORIZATION**
> 本文件只定义给实施人、环境负责人和审批人交接的配置与证据。它不是 Compose、Keycloak Realm import、Ingress manifest、数据库迁移或远程执行脚本；任何人均不得把本文件、其他 Draft PR 或 CI PASS 视为安装/合并许可。
>
> 目标：一个不共享既有 V2/staging/生产资源的 **复盘和视频学习只读 Canary**。唯一数据 Scope：`prp.reviews.read`、`prp.video.read`；唯一 MCP 工具：`prp_reviews_list`、`prp_video_folders`、`prp_video_progress`。

## 1. 实施版本与已有证明

- 源码依赖：#219 → #224 → #278 → #298 → [#312](https://github.com/micor-cjj-spec/matrix-prp/pull/312)；第一方身份授权说明来自 [#349](https://github.com/micor-cjj-spec/matrix-prp/pull/349)。整合验证由 **CI-only、禁止合并**的 [#353](https://github.com/micor-cjj-spec/matrix-prp/pull/353) 证明。
- **最后一次已核实的组合测试 SHA**：`60ccba8d9115deecc9fa0b3f5c1a82569b4dfb9e`，对应 [Push 7/7](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45055881360) + [PR 6/6](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45055886640)；包括合成用户、一次性 Keycloak JWT/PKCE、Chromium 实际网页勾选授权与回调、撤销验证。
- 上述测试使用 Runner 内旧形态 `prp-mcp` Realm 和临时签名材料，**没有证明**拟议的 `prp-mcp218` Realm 在实际目标安装、真实 ChatGPT 签名或 G0/B2 恢复。
- 在目标被指定、变更获批后，必须锁定**新的 exact commit/image digest** 并重新确认与当时 `main` 的兼容性；此处旧 SHA 不是发布版本选择，也不是批准证据。

## 2. 隔离资源交接矩阵（所有值待实际负责人核实）

| 对象 | 专属目标约束 | 负责人必须提供的脱敏证据 | 目前 |
| --- | --- | --- | --- |
| 宿主/命名空间 | 独立主机或经审批的等效隔离边界；明确 CPU/内存/磁盘、运维负责人 | 主机/namespace 的**非敏感代号**、资源上限、使用权确认 | **UNASSIGNED** |
| 容器归属 | 专属 Compose project `prp-mcp218-...`、不重名的专属 network/容器/卷；不碰 V2 | `docker compose config` 审查结论、名称冲突/监听占用的**脱敏**检查 | **UNASSIGNED** |
| PRP 数据 | 新的空 MySQL schema `matrix_prp_mcp218_...`、独立卷和账号；仅两名合成 Owner | 无旧 `matrix_prp`/V2 数据迁入的只读证明、测试数据种子计划 | **UNASSIGNED** |
| Keycloak 存储 | 全新 `prp-mcp218` Realm 的独立 Keycloak DB/卷/密钥和回滚边界；不得修改 `auth-test` | 新 Realm 归属、Client/Scope 导入评审结果、签名/JWKS 归属 | **UNASSIGNED** |
| MCP Resource | 审批后专用 HTTPS `https://mcp218-<assigned-host>/api/mcp`；不是 `prp-test.micor.top` | DNS 所有权与真实解析、可信 TLS、反代 path/method 允许表 | **UNASSIGNED** |
| OAuth Issuer | 审批后独立 HTTPS `https://auth-mcp218-<assigned-host>/realms/prp-mcp218`；不是 `auth-test.micor.top` | 实际 OIDC Discovery、JWKS、Issuer/Token Audience 的脱敏对照 | **UNASSIGNED** |
| 独立 SPA | 新 Resource Origin 单独提供 PRP 前端与 `/prp/me/mcp-link/callback`，构建时 Issuer 固定为上述新 Realm | 新 SPA 产物 digest、回调/授权端点来源、路由与浏览器受控验证 | **UNASSIGNED** |
| 独立备份/恢复 | 针对**本目标**的 PRP DB、Keycloak DB/Realm 和必要配置；不可共享/删除 V2 卷 | 备份位置代号、时间戳、**隔离恢复成功**的可复核收据及回滚责任人 | **UNASSIGNED** |
| 变更授权 | G0 目标审查、B2 恢复证据、安装与公网路由变更均需各自明确批准 | 审批人、变更窗口、受控凭据的**引用 ID**（不要贴原始凭据） | **NOT_APPROVED** |

**缺任何一项 = NO-GO。** “UNASSIGNED” 代表尚未得到经核实的资料，不等于资源不存在；不得据此选择任何已经运行的端口、服务器、数据库或 Realm 进行复用。

## 3. 应用与身份配置映射（期望值，不是部署文件）

| 层 | 期望合同（获批后复核） |
| --- | --- |
| PRP MCP | `MATRIX_PRP_MCP_ENABLED=true`、`MATRIX_PRP_MCP_OAUTH_ENABLED=true` 只能在独立获批实例生效；现有环境不修改 |
| 最小写入边界 | `MATRIX_PRP_MCP_WRITE_ENABLED=false`、`MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED=false` |
| 复盘/视频专用开关 | `MATRIX_PRP_MCP_REVIEW_VIDEO_READ_TOOLS_ENABLED=false` 初始关闭；后续必须有单独启用许可才能设 true |
| 公布数据 Scope | 精确 `MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES=prp.reviews.read,prp.video.read`；绝不从 V2 拷贝 8 Scope |
| Keycloak Resource | 新 Realm `prp-mcp218`、bearer-only `matrix-prp-mcp218-resource`，Audience 精确新 MCP Resource URL |
| ChatGPT Client | **Client ID** `https://chatgpt.com/oauth/client.json`；精确回调 `https://chatgpt.com/connector_platform_oauth_redirect`；PKCE S256、受限 `private_key_jwt`/JWKS/CIMD；无通配 DCR |
| 第一方 Client | **仅在新 Realm 复用标识字符串** `prp-first-party-link`（现有 SPA 固定安全校验）；精确新 SPA callback；不得复用旧 V2 Client 实体、Owner 或 Grant |
| SPA 构建 | `VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT` 必须指向新 Issuer 的 `/protocol/openid-connect/auth`，不得引用现有 `auth-test`、生产或旧 V2 编译产物 |
| 用户/授予 | 先创建 A/B 两个**合成** Owner，再验证 UID 并只允许必要的 expanded-user-ids；`POST /api/mcp/clients` 是**完整替换 Scope 集**，Owner 要明确批准，默认不勾选 |

**强制排除**：当前 V2 端口 `18082`、旧 stage `18081`、生产 `11000`；既有 `prp-mcp-v2`、`prp-mcp-stage`、`prp-mcp-oauth-stage` 容器、`prp-test` 和 `auth-test`，共享数据库/卷、真实用户数据、现有 OAuth 客户端签名密钥。不能以“相同 Client ID 字符串”作为复用真实 Client 的依据。

## 4. 编排与公网路由包：待实施人提交的**最小内容**

在目标资源和审批均真实具备后，由独立实施人另行提交**新的、目标专用、可审查**配置；本仓库现有旧 Stage Compose 不得直接作为目标包：

1. **容量与归属**：专属 Compose project、独立 Docker network、独立 DB/Keycloak/PRP 容器、只读 SPA 服务、显式 CPU/内存/卷/端口；无共享 hostPath、生产/现有 V2 secrets 或外部挂载。
2. **可逆服务依赖**：独立 MySQL/Keycloak 数据卷、健康检查、启动顺序、构建工件 SHA/digest、最小环境变量及默认关闭开关；绝不通过迁移现有生产 schema 初始化。
3. **受控 HTTPS 暴露**：只允许审批的 MCP Resource/Protected Resource metadata、Issuer OIDC discovery/JWKS/token/authorize、第一方 start/finish/callback 与 SPA 路由；每个实际 path/method 都须从当前源码核对，不授权全域 `/api/**` 或通配 redirect。
4. **撤销与回滚**：先撤销新 Canary 的 client grant/关闭专用工具开关，再停用隔离路由；对独立数据卷执行经过 B2 实际验证的恢复；不得对任何共享 Compose project 执行 `down -v`、批量删除客户端、重写 Flyway 历史或撤销既有 V2 授权。
5. **工件安全**：仓库只保留无密钥的清单/镜像 digest/脱敏审查结果；数据库账号、SSH、TLS 私钥、JWT、用户数据及 Keycloak client 实际密钥不得写入 PR、Issue、日志或模板。

## 5. 可立即执行的**离线**门禁（不安装、不联网）

使用现有工具，不新造部署入口。把获批目标的**无密钥**方案填进一份本地 JSON（不得提交真实敏感数据），并执行：

```sh
node --test app/scripts/mcp218-canary-plan.test.mjs
python3 -m unittest discover -s app/deploy/mcp218-canary -p 'test_*.py'
python3 app/deploy/mcp218-canary/check_offline_contract.py /path/to/nonsecret-plan.json
```

返回 `MCP218_OFFLINE_CONTRACT_PASS_ONLY_NO_DEPLOY_AUTHORIZATION` **只证明 JSON 格式、独立命名、禁用开关、两 Scope 和候选 Realm/Client 静态相符**；不会校验实际 DNS/TLS/端口归属、真实 G0/B2 收据、OpenAI 私钥或操作许可。任一阻塞状态不可据此改成 PASS。

## 6. 目标级执行次序及停机门槛

- **G0 · 无状态核验**：审查目标主机归属、资源预算、域名/证书/监听冲突、专属 Compose/Ingress 静态渲染、镜像来源/哈希、审批边界。任何未知项：**STOP**。
- **B2 · 先证实恢复**：独立目标 DB/Realm/路由快照与**实际在隔离副本恢复**的签署证据。只有 backup 文件、理论回滚或旧 V2 收据：**STOP**。
- **单独变更授权**：实施包 exact SHA、目标资源清单、审批人/窗口/回滚收据都核对一致后，才可申请新 Realm、DB、SPA、Ingress 的安装权限。**此文档不提供这些操作的批准。**
- **单独测试授权**：获批后才创建合成 Owner A/B、在新 Realm 安装两个精确 Client/签名密钥、开启只读三工具；验证零授权拒绝、只读 Scope/工具恰好匹配、用户隔离、跨 Owner 拒绝、最小响应上限、Grant 撤销后 401、浏览器回调安全。
- **真实 ChatGPT Connect 独立许可**：官方 Client assertion/PKCE/Issuer/Resource/owner 映射逐项在新目标核对；不将 CI 中模拟的签名视为真实 OpenAI 连接。通过也不自动授予生产或主线合并权。
- **失败即停止与可逆收口**：任何越权工具、额外写入、错误 Audience、V2 数据命中、TLS/回调异常、恢复失败，停止新环境后续步骤并按独立获批计划回滚；不影响旧系统。

## 7. 当前交接决议

| 决策 | 结论 |
| --- | --- |
| 离线合约和一次性 Chromium/JWT 测试 | **历史 exact-head CI PASS；不代表目标安装** |
| 可立即执行的独立目标部署工件 | **未提交、不可推定存在** |
| 可验证的目标资源、DNS、TLS、恢复及变更审批 | **未提供，均保持 NO-GO** |
| #218 实机安装、真实 ChatGPT Connect、合并与生产发布 | **NO-GO / NOT AUTHORIZED** |

下一步应由目标环境负责人提供第 2 节所需的**脱敏资源与实际恢复证据**，由实施人准备并审查专属配置后再单独申请授权。没有这些资料，不得填假值、生成可运行的替代部署或改用现有 V2 进行试验。
