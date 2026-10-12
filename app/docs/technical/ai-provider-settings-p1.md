# Matrix AI P1 — 多模型服务商与个人 API Key

## 范围

- Web/PWA「我的 → AI 模型与接口」和「聊天」模型切换入口
- 固定支持 DeepSeek、Kimi、OpenAI、Gemini、Claude、Qwen；可输入模型 ID（不是自定义 API URL）
- 个人 API Key AES-256-GCM 加密存储、用户 ID 与 provider 绑定为附加认证数据（AAD）
- API 仅返回 `configured` / `personalKey` 布尔值，永不返回密钥、密文或最后几位
- 账户互相隔离；不能读取、更改、删除别人的密钥
- 支持保存/替换/删除密钥、模型偏好、少量 Token 的真实连通性测试（计入既有额度）
- OpenClaw / Codex 继续默认关闭，不执行命令，不自动开放财务/健康等业务工具

## 生产上线前置操作

1. 在隔离环境完整备份并恢复演练 MySQL `matrix_prp`、视频目录和 systemd 配置。确认旧库与 V1～V7 的一致性。
2. 保持 `MATRIX_PRP_FLYWAY_ENABLED=false`，按照 `safe-db-migrations-p0.md` 显式登记旧库 V7 baseline；从 V7 迁移到 V8、V9。若当前 Flyway 已到 V8，则只执行 V9。严禁清卷、重建旧库、baselineOnMigrate 或 clean。
3. 设置 **持久、私密且独立的加密密钥** `MATRIX_PRP_AI_KEY_ENCRYPTION_SECRET`，要求标准 Base64 编码的 32 字节随机值（示例生成命令：`openssl rand -base64 32`）。不要复制例子当密钥、不要写入仓库、不要打印密钥。请在受保护的异地位置安全备份加密主密钥；丢失将无法恢复已保存的个人 API Key。轮换密钥需要专门的解密/重新加密迁移流程，不可直接覆盖。
4. 后端 systemd 环境独立设置上述密钥，按现有部署流程发布代码、验证 V9、启动服务；前端按现有 `/prp/` 子路径发布。不能先打开 Flyway 自动迁移并直接对未知旧库重启。
5. iPhone PWA、普通用户/管理员交叉测试：保存/替换/删除、跨用户隔离、无配置时友好失败、重新登录模型偏好仍在、SSE Nginx 反向代理、V9 验证及原有视频/健康/推送模块回归。
6. 需要正式生产供应商密钥和余额才可进行真实连通性验收；GitHub CI 不接触任何外部收费 API。

## 兼容与策略

- 已有 `MATRIX_PRP_DEEPSEEK_API_KEY`、`MATRIX_PRP_DEEPSEEK_MODEL` 是兼容回退：用户未设置自己 DeepSeek 密钥时仍可以使用原来的服务器配置，受现有全站/用户用量约束。生产环境若不希望朋友们使用共享 Key，应清除该环境变量或者增加专门的管理员共享策略。
- 若无 `MATRIX_PRP_AI_KEY_ENCRYPTION_SECRET`，旧服务器 DeepSeek 回退仍可聊天；保存/读取个人加密密钥将拒绝操作，不会明文落库。
- 接口固定 provider 域名，**不**接收客户端指定的 URL，阻止代理任意内网地址。Qwen 默认北京地域旧域名；需其它地域/工作空间可在后续版本加入服务端配置与白名单。
- 连接测试调用模型生成短文本并产生少量供应商费用，不是纯 DNS 检查。计入原有月度用量；额度是预留估算，不是供应商真实账单封顶。
- 同一会话允许切换模型（历史消息仍归该账号所有），消息不记录逐条模型归属，本阶段 UI 仅显示通用「AI」标签。
- 每个模型实际可用性、参数限制、账号授权由供应商决定；“预设”是示例，并不保证每个账号可调用。
- 密钥经过 HTTPS 传输。只应在用户本人受信设备输入，避免日志、抓包和第三方浏览器插件暴露。
- 本 PR **只合并 GitHub 代码**，不触碰云服务器、生产 MySQL 或真实 API 密钥。下一阶段 OpenClaw Gateway 需要再设计内部认证、工具权限和任务审批；Codex Worker 必须使用隔离执行环境。
