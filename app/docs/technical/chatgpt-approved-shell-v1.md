# PRP 纯聊天批准的远程命令通道（候选 V1）

状态：**DRAFT / 未合并 / 未安装 SSH 身份 / 未启用 / 禁止生产执行**。

## 用户交互（无需 MCP 或审批页面）

- GPT 展示将执行的**完整 Shell 命令**、目标主机、执行账号与风险。
- 用户在同一聊天中回复「可以」「批准」或「执行」。
- GPT 仅对**这一条已展示的原样命令**发起执行，不得根据一次批准自动执行后续新命令。
- GPT 使用现有 GitHub 连接器在 Issue #277 发布**加密评论**；GitHub Actions 经独立 SSH 账号执行，写回加密输出。GPT 读取并解密结果。
- 对任何新的命令必须重新征得批准。用户拒绝或修改后，应取消旧提议并展示新命令再确认。

**注意**：这是一条基于 GPT 按照当前对话执行工具操作的授权流程，不是可被服务器独立证明的人类审批签名。GitHub 执行端验证真实 GitHub 所有者身份、指定 Issue 和不可重放的密文；它无法判断用户是否真的在聊天中说了「批准」。若今后要求强认证/不可抵赖审计，需要额外审批机制。本方案按照用户选择，不增加 MCP、独立 Web 页面或密码二次验证。

## 为什么不能直接把 Shell 命令放进 GitHub 评论？

PRP 主仓库公开。Issue 正文、评论和 GitHub Actions 输出不能存放任意命令明文或 stdout/stderr，因为命令/输出可能包含内部路径、敏感信息、数据库连接参数。Base64 **不是加密**。

为了复用当前 GitHub 连接器可用的「发 Issue 评论」入口，使用 OpenSSL CMS **AES-256-GCM 加密**：

- 服务器保存一份**root 仅可读的 RSA 私钥**；
- PRP 仓库只保存对应的公开证书（完成独立服务器初始化并核验指纹后才能添加）；
- GPT 在获得用户批准后，使用公钥加密包含 command/target/jobId/nonce/过期时间/临时结果证书的 JSON；
- Issue #277 只接收固定格式的密文评论；
- 服务器在隔离 SSH 通道内解密；执行后使用 GPT 本轮提供的**临时结果公钥**加密 stdout/stderr；
- GitHub Actions 只把**密文结果**写回 Issue，GPT 在当前会话中用本轮临时私钥解密。

不对外发布命令明文、结果明文或密钥。客户端临时私钥不得写入 Issue、仓库、Action 日志、ChatGPT 普通消息或共享文档。若会话丢失该临时私钥，该批次原始输出可能无法恢复；不自动重跑命令。

## 现有代码边界

- app/deploy/chat-shell/protocol.py：命令加密、结果解密、严格 JSON 与时效校验。
- app/deploy/chat-shell/github_bridge.py：只接受真实所有者 micor-cjj-spec 在**固定公开 Issue #277** 发出的精确前缀评论，并通过独立 SSH 强制命令执行。
- app/deploy/chat-shell/prp_shell_executor.py：只读取加密 stdin，校验过期/目标/命令长度/nonce，主机本地一次性认领，再切换为**独立非 root 用户 prp-shell**执行。
- app/deploy/chat-shell/gateway.sh：独立 SSH 身份只接受 SSH_ORIGINAL_COMMAND=run。
- .github/workflows/prp-chat-shell.yml：候选 workflow；**在 PR 尚未合并到 main 时不会生效**。独立 environment production-shell，尚无凭据。
- .github/workflows/chat-shell-contract.yml + test_chat_shell.py：不访问生产、无 SSH secrets 的离线协议测试。

**没有命令白名单**；但当前 Shell 受 Linux 用户权限约束，不能隐式获取 root。默认单命令最多 30 秒，最长命令 8192 UTF-8 字节，输出每流最多 10 KiB。超时只终止前台进程组，不能保证清理所有人为脱离进程组的后台子进程。

## 后续生产启用前的独立准备（本 PR 没有执行）

1. 审核并冻结代码 SHA，验证所有 CI；单独确认允许合并 workflow，确认不会触发 PRP 自动发布。主分支保护、publication-hold 与现有部署门禁不能绕过。
2. 由可信管理员在服务器上创建两个相互隔离的账户：
   - prp-chat-shell：专用 SSH 接入、强制只执行 gateway.sh，禁止 SFTP/端口转发/交互式 Shell；
   - prp-shell：实际执行命令的低权限账号，不属于 sudo 等特权组。
3. 服务器独立生成 root-only RSA 私钥/公开证书。将**公开证书**经 SHA256 指纹核对后添加到可信 main 仓库路径；私钥永久留在服务器，不能交给 GitHub、GPT 或普通执行账号。
4. 根管理员从审阅过的固定版本安装协议脚本、网关与执行器；精确配置 sudoers 仅允许运行这一条固定 Python 执行器命令（无参数）。配置 root-only 重放 SQLite 目录，不触碰现有 prp-deploy 和 prp-inspect SSH 账号。
5. 配置 GitHub Actions 独立 production-shell 环境中的 PRP_SHELL_HOST、PRP_SHELL_SSH_KEY、PRP_SHELL_KNOWN_HOSTS。不得复用 PRP_DEPLOY_* 或发布密钥，不要授予 workflows: write 或 contents: write。
6. 先在**隔离测试机**验证带符号命令、unicode、标准输出/错误、退出码、重复评论、非 owner 评论、重放、证书错误、过期、超过 30 秒、输出截断、撤销 SSH 密钥。最后才考虑在正式 PRP 服务器上启用。

现有 GitHub 连接器**不能设置 GitHub Actions Secrets**，也不能直接安装服务器 SSH 文件。因此现阶段无法替代管理员完成第 2–5 步。不要误将提交 PR 或 CI 绿灯表述为服务器已经能执行命令。

## 本地离线验证

    python3 -m unittest discover -s app/deploy/chat-shell -p 'test_*.py' -v

通过上述测试只证明协议局部行为，不等于真实 ChatGPT 会话、GitHub Actions、SSH 或正式环境验收。

## 风险与回滚

- 用户批准仅针对特定命令；命令/目标发生任何变化必须重新批准。
- GitHub 事件的 owner 身份只能证明提交评论的 GitHub 用户，不证明实际聊天批准；账户被盗即会产生严重风险。
- GitHub Actions 的运行和发回结果可能由于队列、网络、超时而不确定；重复触发只能拒绝，不自动重跑。
- 撤销独立 SSH 密钥和 production-shell 环境 Secrets 即能切断该通道；现有部署路径不应受到影响。
