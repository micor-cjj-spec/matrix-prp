# PRP：ChatGPT 对话批准后的加密 Shell 通道 V1

> **状态（2026-11-22）：技术端到端验收通过；执行通道默认关闭；生产业务应用发布仍受控。**
>
> 这一状态并不意味着 ChatGPT 获得永久远程执行权限。每次新命令都须由用户明确批准；开启服务器执行窗口还需要独立、限时的 root 侧授权。

## 1. 验收结果与证据

- GitHub 基础实现：PR [#273](https://github.com/micor-cjj-spec/matrix-prp/pull/273) 已合并。
- 故障分类：PR [#296](https://github.com/micor-cjj-spec/matrix-prp/pull/296) 已合并。
- SSH 私钥末尾 LF 兼容修复：PR [#299](https://github.com/micor-cjj-spec/matrix-prp/pull/299) 已合并；合并后 CI [44989571567](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44989571567) 成功。
- 单次真实端到端验证：运行 [44990969307](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44990969307) 的 `command` 作业成功。入口为 Issue [#277 的加密评论](https://github.com/micor-cjj-spec/matrix-prp/issues/277#issuecomment-7074957553)，输出为同 Issue 的[加密结果评论](https://github.com/micor-cjj-spec/matrix-prp/issues/277#issuecomment-7074959646)。
- 经当次生成、只用于该次请求的临时结果私钥解密后，响应字段显示 `exitCode=0`、`timedOut=false`、`truncated=false`、`stderr=""`，`stdout` 为：

  ```text
  PRP_SHELL_E2E_OK
  prp-shell
  ```

- 用户随后从服务器 root 终端删除 `/etc/matrix-prp-chat-shell/execution.enabled`，并删除仓库变量 `PRP_CHAT_SHELL_ENABLED`，验证输出为 `E2E SECURELY CLOSED`。最终撤销证据记于 [PR #299 评论](https://github.com/micor-cjj-spec/matrix-prp/pull/299)。
- 发布保护：main 保留 `app/deploy/publication-hold.json`。上述验收没有将 PRP 业务应用部署到生产；自动部署的 `publish` 步骤在合并后为 `skipped`。

**验收范围限定：** 证明一次事先批准的、无副作用命令能够以 `prp-shell` 执行，并完成 CMS 加密回传和解密。没有验证任意复杂脚本、后台任务、长期授权、持久会话或在无人监督下执行的安全性。

## 2. 用户交互与授权

1. ChatGPT 在发起前完整展示拟执行的 Shell 命令、目标 `micor-server`、非 root 执行账号 `prp-shell`、预期影响与风险。
2. 用户在当前对话中针对**这条原样命令**回复批准；“继续”或旧命令的批准不得被复用到不同命令。任何修改都要重新展示并重新获得批准。
3. 默认关闭的执行窗口须经过单独授权后才可临时启用。授权窗口的存在不替代逐条命令批准；逐条聊天批准也不等于允许永久打开执行窗口。
4. ChatGPT 使用仓库公钥证书构造短期加密请求，在固定公开 Issue #277 发表**密文**；GitHub Actions 验证 owner、Issue 和事件类型后，以强制命令 SSH 接入。
5. 服务器检查 root-only 开关、任务字段、时效和不可重放 nonce，以独立低权限账号 `prp-shell` 执行；结果再用该次请求的临时结果证书加密。
6. GitHub 只保存结果密文；发起方用本次临时私钥解密并核对任务 ID、退出码、stdout/stderr 和超时/截断标志。任务状态不确定时**不自动重试**。
7. 测试完成立即撤销双开关，并核对生产发布锁仍存在。

**审批边界：** GitHub 能验证评论来自指定 GitHub owner，但不能独立证明用户确实在 ChatGPT 对话中批准了命令。聊天批准目前是会话执行流程的约束，**不是独立的密码学签名或不可抵赖审计**。如未来需要正式生产环境的长期自助执行，必须单独设计可核实的授权边界，不得靠永久启用两个开关来“简化操作”。

## 3. 组件与安全边界

| 组件 | 职责 |
| --- | --- |
| `app/deploy/chat-shell/protocol.py` | OpenSSL CMS AES-256-GCM 双向封装、一次性结果证书、严格 JSON、时间戳和任务 ID 校验 |
| `app/deploy/chat-shell/github_bridge.py` | 接收 owner 的加密评论、使用独立 SSH 凭据发送、把密文结果写回 Issue；仅打印固定错误类别 |
| `app/deploy/chat-shell/gateway.sh` | 只接受 `SSH_ORIGINAL_COMMAND=run`，无交互式 Shell |
| `app/deploy/chat-shell/prp_shell_executor.py` | root-owned 入口检查执行开关、解密/验签协议字段、一次性任务认领，降权到 `prp-shell` 执行 |
| `.github/workflows/prp-chat-shell.yml` | `issue_comment` 执行路径（默认关）与 `workflow_dispatch` 空请求连通测试 |
| `.github/workflows/chat-shell-contract.yml` | 不使用服务器凭据的离线协议与回归测试 |

- 加密要求：服务器 RSA 私钥仅留服务器 root 目录；仓库只放公钥证书；结果私钥仅在发起侧当前任务内短暂保留，不得放入 Issue、日志、仓库或普通聊天正文。
- 评论格式仅允许 `/prp-shell-v1 <job-uuid> <ciphertext>` 与 `/prp-shell-result-v1 <job-uuid> <ciphertext>`；Base64 本身不是加密。
- **双开关默认关闭：**
  - 仓库变量 `PRP_CHAT_SHELL_ENABLED=true` 才允许 GitHub Actions 的 `command` 作业启动；
  - root-only 文件 `/etc/matrix-prp-chat-shell/execution.enabled` 必须为 root:root、0400，精确内容 `PRP_CHAT_SHELL_ALLOW_V1\n`；服务器在解码 CMS 密文前检查该文件。
- 任何一道开关撤销即可阻止常规链路的新执行请求。两个开关的启用/撤销必须作为**独立的、受控的管理操作**进行。
- 执行器绑定账号 `prp-shell`，无 sudo/root 权限；`prp-chat-shell` SSH 账号仅用于受限网关。即便非 root Shell 仍可访问其文件权限允许的资源，因此不能把任意 Bash 当作低风险工具。

## 4. 范围限制与风险

- 单请求最大命令约 8192 字节；执行超时设定为 1–30 秒；密文有效期约 180 秒；stdout 与 stderr 每流最多记录约 10 KiB。队列延迟导致任务过期时，应拒绝而非延长或重放。
- 当前**没有命令白名单**；执行虽降权，命令仍可能修改其权限范围内的文件。必须按实际影响逐条人工批准。
- 超时处理会终止前台进程组，但不保证清理故意脱离进程组的后台子进程。不得将该通道视为有完整沙箱隔离。
- GitHub 工作流失败可能发生在评论校验、SSH、远端处理或回写等任意阶段。不要仅凭通用失败码推断命令“绝未执行”；检查一次性任务认领和返回证据后再决定是否重新提出新任务。
- 输出丢失本轮临时私钥后可能无法恢复，不能为“找回输出”擅自重跑敏感命令。
- **不支持**把“我以后在 GPT 里说批准”理解成自动提权、永久开放远程 Shell 或绕过 root 安全闸。

## 5. 安全关闭与状态核验（服务器 root）

本段只包含**撤销**和验证命令，不会开启执行权限。

```bash
rm -f /etc/matrix-prp-chat-shell/execution.enabled

gh variable delete PRP_CHAT_SHELL_ENABLED \
  --repo micor-cjj-spec/matrix-prp 2>/dev/null || true

test ! -e /etc/matrix-prp-chat-shell/execution.enabled

VALUE="$(gh variable get PRP_CHAT_SHELL_ENABLED \
  --repo micor-cjj-spec/matrix-prp 2>/dev/null || true)"

test "$VALUE" != "true" && echo "E2E SECURELY CLOSED"
```

核验结果为 `E2E SECURELY CLOSED`，意味着这两项被检查的执行开关已关闭。必须同时确认与业务应用部署独立的 `app/deploy/publication-hold.json` 未被撤销。

**恢复临时测试窗口**不是例行默认操作：只有用户再次明确允许具体无副作用测试及限时授权，管理员才可按经审阅流程设置两个开关，并预设服务器侧自动撤销和失败回滚。测试结束立即主动撤销，不等待计时器。

## 6. 后续迭代边界

V1 已完成单次技术 E2E，但**“无需手动服务器授权即可在日常聊天中永久执行任意 Shell”不是本次交付范围**。若继续提升日常交互，优先将高频操作收敛为细粒度、可审计的只读能力，使用明确的参数约束、授权有效期和范围，而非永久开启通用 Bash。任何设计修改需要独立安全评审、测试、用户批准合并，且不应解除既有 PRP 业务发布锁。

历史初始化过程、早期未安装状态和错误分析保留在 PR #273、#296、#299 的审查记录中；以本文的当前状态与最新验证证据为准。
