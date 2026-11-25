# PRP 纯聊天批准的远程命令通道（候选 V1）

状态：**DRAFT / 未合并 / 已完成服务器受限 SSH 网关与环境凭据配置 / 执行开关默认关闭 / 尚不能从 GPT 触发真实命令**。

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
- .github/workflows/prp-chat-shell.yml：候选 workflow；**在 PR 尚未合并到 main 时不会生效**。独立 environment production-shell 的凭据已配置；仓库级开关 `PRP_CHAT_SHELL_ENABLED` 默认未设置，任意命令执行关闭。另有只发送空请求的 `workflow_dispatch` 联通测试。
- .github/workflows/chat-shell-contract.yml + test_chat_shell.py：不访问生产、无 SSH secrets 的离线协议测试。

**双重默认关闭保护：** GitHub Actions job 需要显式设置仓库变量 `PRP_CHAT_SHELL_ENABLED=true`；服务器新执行器也需要 root:root 0400 的 `/etc/matrix-prp-chat-shell/execution.enabled` 文件，**内容必须逐字为** `PRP_CHAT_SHELL_ALLOW_V1\n`。任一条件不存在，均不能通过常规链路执行真实命令。此标志只在单独获得生产启用授权、所有联调验收后由管理员创建。启用后每组新命令仍须用户在聊天中重新批准。撤销服务器标志或 GitHub 变量任一项即可阻止后续新任务。

**关闭状态下的攻击面缩减（待安装）：** `process_request` 首先要求 root-only `execution.enabled` 文件，然后才进行 base64 解析、OpenSSL CMS 解密及任务时效检查。这样即使攻击者拿到了专用 SSH 密钥，在服务器开关关闭时也无法让 root 进程处理自定义 CMS 密文。此项顺序调整属于较新的 PR 分支代码，**服务器上已安装的 `fa2afff2` 执行器尚未包含**，不可把它误判为生产已生效保护。

**本机已安装版本注意：** 服务器此前从固定 commit `ff75e80a` 安装的旧版执行器不包含上述主机端标志检查。当前仅更新了 PR 分支源码，**没有更新服务器 /usr/local/sbin/prp-chat-shell-executor**。在将该能力对外开放前必须先按固定、安全审查后的新 SHA 离线验收并原子更新服务器安装文件，不能仅设置 GitHub 变量。新版本的空输入仍会以退出码 2 拒绝，所以 `connectivity-smoke` 可在执行开关关闭时验收 SSH 连通性。

**没有命令白名单**；但当前 Shell 受 Linux 用户权限约束，不能隐式获取 root。默认单命令最多 30 秒，最长命令 8192 UTF-8 字节，输出每流最多 10 KiB。超时只终止前台进程组，不能保证清理所有人为脱离进程组的后台子进程。

## 后续生产启用前的独立准备（本 PR 没有执行）

1. 审核并冻结代码 SHA，验证所有 CI；单独确认允许合并 workflow，确认不会触发 PRP 自动发布。主分支保护、publication-hold 与现有部署门禁不能绕过。
2. 由可信管理员在服务器上创建两个相互隔离的账户：
   - prp-chat-shell：专用 SSH 接入、强制只执行 gateway.sh，禁止 SFTP/端口转发/交互式 Shell；
   - prp-shell：实际执行命令的低权限账号，不属于 sudo 等特权组。
3. 服务器独立生成 root-only RSA 私钥/公开证书。将**公开证书**经 SHA256 指纹核对后添加到可信 main 仓库路径；私钥永久留在服务器，不能交给 GitHub、GPT 或普通执行账号。
4. 根管理员从审阅过的固定版本安装协议脚本、网关与执行器；**网关脚本为 root:root 0555（供 SSH 非 root 账号执行），执行器 root:root 0500，protocol.py root:root 0400**。精确配置 sudoers 仅允许运行这一条固定 Python 执行器命令（无参数），不得授予 shell、docker、sudo 通配符。配置 root-only 重放 SQLite 目录，不触碰现有 prp-deploy 和 prp-inspect SSH 账号。
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

## 2026-11-22 手动初始化进度

- 已在 Debian 13 生产服务器上创建 `prp-shell` 和 `prp-chat-shell` 两个账号；root-only 加密密钥目录、重放目录和 RSA 证书已存在。
- 已在服务器本地按固定 commit `ff75e80a` 执行全部 11 项离线测试，全部通过；公钥证书 SHA-256 指纹匹配。校验通过后，执行器、网关与协议模块安装在 `/usr/local/sbin/`。
- 安装时网关误设为 `0500`，**必须先改为 `0555`**，否则非 root 的 SSH 接入账号无法启动它；脚本仍须 root 所有且父目录不可写。
- 专用 SSH authorized_keys、sudoers、Actions Secrets 已完成安装与本机空请求验证；**尚未将触发工作流合入 main，也未开启 repo-level 执行开关**，真实 GPT 命令执行通道不可用。
- 上述 11 项是离线单元测试，尚不能替代独立 SSH 授权、Actions 端到端测试与安全审查。GitHub CI 尚在排队。
- 2026-11-22 后续进度：已安装独立强制命令 SSH 网关，**本机执行空请求会返回预期拒绝**；GitHub `production-shell` 环境已配置 main-only 策略以及三个独立 Secrets（HOST / SSH_KEY / KNOWN_HOSTS）。此前的“尚未添加”项已完成，不等于 GitHub Runner 外部联通已验收。
- **新增默认关闭开关：** GitHub Actions `command` job 必须同时满足 `vars.PRP_CHAT_SHELL_ENABLED == 'true'` 才能执行。**不要在完成正式安全评审和端到端验收前设置该变量。**
- **只用于验证的工作流：** `workflow_dispatch` 会启动 `connectivity-smoke`，它使用已经配置的 Secrets 从 GitHub Runner 访问强制网关，仅发送**空输入**，要求网关返回 `PRP_SHELL_REQUEST_REJECTED`；绝不传递或执行真实命令。该工作流必须存在于 main 才能执行；请先通过所有 CI、审核并单独批准只启用测试通道的合并步骤。
- **互斥注意：** 这套默认关闭开关是部署期间的保护，不是 ChatGPT 用户批准的密码学验证。不能把“未启用变量”解释为已完成端到端验收。
