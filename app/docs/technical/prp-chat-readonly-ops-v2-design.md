# PRP ChatGPT 固定只读运维 V2：最小设计（评审稿）

> **状态：仅设计 / 尚未开发 / 尚未部署 / 尚未授权。** 对应 [Issue #309](https://github.com/micor-cjj-spec/matrix-prp/issues/309)。
>
> V1 单次加密 Shell 端到端验收已成功（[Actions 44990969307](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44990969307)），但其通用 Bash 通道在验收后已恢复**双重默认关闭**。V2 的目标不是把 V1 永久打开，而是让少量固定只读查询在 ChatGPT 对话里完成。

## 1. 场景与边界

用户想直接说「查看 PRP 的 CI、磁盘占用、健康状态」，无需每次登录服务器或前往 GitHub GUI 点审批。安全边界：

- 仅**明确列出的查询能力**；不提供 Bash、任意命令字符串、任意路径、任意 URL、进程 PID、环境变量、任意 SQL、任意日志或容器 API 操作。
- 每次使用仍需在当前聊天明确批准查询和数据范围；用户对 V1 其他命令的批准不可继承。
- **不以 GitHub owner 身份冒充聊天中的强签名批准**：现有 GitHub 身份校验只证明评论来自指定所有者账号，不能独立证明聊天批准。
- 不修改服务器文件、数据库、业务配置，不启动/停止容器，不部署。V1 的 root-only 执行开关、GitHub 执行变量以及 `app/deploy/publication-hold.json` 不变。

## 2. V2 首批能力（最多三项）

| 用户需求 | 内部 operation | 数据来源 | 允许参数 | 返回内容 |
| --- | --- | --- | --- | --- |
| 看 GitHub CI 当前状态 | `github_ci_status` | **现有 GitHub 连接器直读**，不访问服务器 | 固定仓库和默认分支；最多 1 个已知 workflow run ID | workflow、状态、结论、URL、时间（仅 GitHub API 的可公开字段） |
| 看服务器系统盘空间 | `host_root_fs_usage` | 待审批的独立低权限只读采集器 | **无参数** | totalBytes、usedBytes、freeBytes、usagePercent；仅根文件系统 |
| 看 PRP 后端是否可响应 | `prp_app_health` | **优先评估现有 `/api/health` 可用性**；必要时再用独立低权限只读采集器 | **无参数** | `liveness=reachable/unreachable/unknown`、`readiness=unknown`、`probeTimeUTC`；不返回响应原文 |

**已核实的源码依据（尚未核实真实生产可达性）：**

- [HealthController.java](../../backend/src/main/java/com/matrix/prp/common/api/HealthController.java) 已提供 `GET /api/health`：固定 `status=UP`、`service=matrix-prp-backend`、`version=0.1.0`（**硬编码，不代表真实发布版本**）等字段。接口响应成功只能证明后端 HTTP 存活，**不能证明 MySQL、知识库、业务功能就绪**。
- 同一控制器提供 `GET /api/health/runtime`。根据 [RuntimeHealthService.java](../../backend/src/main/java/com/matrix/prp/common/api/RuntimeHealthService.java)，它会验证数据库连接并返回 `status=UP/DEGRADED`，但也带有**知识库绝对路径、运行 profiles 和数据库/持久化状态**。 [SecurityConfig.java](../../backend/src/main/java/com/matrix/prp/config/SecurityConfig.java) 的 `/api/health/**` 是 `permitAll()`；即使上层 Nginx 未对公网开放，此端点仍应按**含内部诊断细节**处理，**不得向 ChatGPT、公开 Issue 或任何 V2 结果返回完整原始 JSON**。
- [phase-1-verification.md](../releases/phase-1-verification.md) 明确记录 MySQL 不可用时 `/api/health` 仍能响应，而 `/api/health/runtime` 是 `DEGRADED`；这证实 **liveness ≠ readiness**。

**首版仅采集最小 liveness 状态**：固定预设本地/已审查的 URL、短超时，HTTP 200 且严格验证响应中的 `data.status=UP` 才映射为 `reachable`。其它 HTTP/网络错误可映射 `unreachable` 或 `unknown`，但不得用 `healthy` 一词暗示全系统可用。只有独立批准、评估数据脱敏与授权后，才可另行提出 readiness 聚合（默认 `unknown`）。

首批**不提供部署版本号**：源码写死的 `0.1.0` 不具备版本证明力；真实容器/提交版本来源尚待核实。

**直接路由原则：** `github_ci_status` 由 ChatGPT 通过现有 GitHub 连接器完成，**不走 SSH**。健康 liveness 先评估经审查的现有 `/api/health` 是否可安全直接访问；仅当确需主机本地信息且不存在安全直接只读源时，才考虑独立 V2 采集器，**不能为凑齐三项而新增 SSH**。

## 3. 主机只读采集候选方案（尚未决定启用）

**独立于 V1 的新通道**：单独 SSH 身份、单独强制命令入口、单独加密证书、单独运行账号；与 `prp-chat-shell` / `prp-shell` / V1 root 执行器物理隔离。不复用 V1 的 root 私钥、sudoers、执行标志或 GitHub Secret。

- 接收端仅接受固定的 `operation` 枚举，无可解释的 Bash 命令或脚本参数；采集器在 Python 内调用固定 `os.statvfs('/')` 等只读 API。严禁 `shell=True`、`bash -c`、`eval`、`exec`、`sudo`、Docker socket 或配置文件写入。
- 采集账号不可获得 root、sudo、部署账号和数据库权限；仅可读取被允许的系统指标；SSH 强制命令禁止交互、端口转发、代理转发和 SFTP。
- GitHub Runner 只充当**加密消息转发**；对调用者做固定 repo/owner/Issue/event/main 的检查；**V2 使用独立路由**，不能让 V1 Issue #277 的评论触发两条工作流。
- 单独执行用户必须可读自己的 V2 解密密钥，但不能访问 V1 root 私钥；因此该密钥**只能解锁固定只读操作**，不可拿去执行通用 Bash。
- 先完成离线权限与攻击面复核；真实服务器上的账号、密钥、SSH 配置、网络、服务安装与常态开放，需要日后分别明确批准。**本设计 PR 不执行这些步骤。**
- 降低滥用风险：一组请求最多一次响应，固定大小输出、有限频率、短请求有效期、nonce 去重、低资源占用、固定超时；如果响应发布失败，记录不确定状态，**不得自动重发主机操作**。
- 如果健康检查必须读取私有 Token、绕过本地 TLS 或使用完整 `/api/health/runtime` 内部 JSON，则**不实现该探针**；仅允许预设的 `/api/health` 存活性请求与**服务器内执行的白名单字段过滤**，或反馈“无法核实”。不得公开 `knowledgeRoot`、`activeProfiles`、内部路径、数据库配置等。

## 4. 精确消息结构（建议契约，不是当前已启用 API）

本节定义解密后的内部数据契约。公开 GitHub Issue **只能承载 CMS 密文**，不能放 JSON 明文。

```json
{
  "version": 2,
  "jobId": "uuid",
  "target": "prp-readonly",
  "actor": "micor-cjj-spec",
  "operation": "host_root_fs_usage",
  "parameters": {},
  "issuedAt": 1795320000,
  "expiresAt": 1795320180,
  "nonce": "32-lowercase-hex",
  "answerCertificate": "one-time-PEM-certificate"
}
```

- `operation` 只允许 `host_root_fs_usage`、`prp_app_health`。GitHub CI 查询不进入此消息协议。
- `parameters` 必须是**空对象**；出现其他键、null、数组、数值、URL、路径、命令都拒绝。
- `jobId` 严格 UUID；`target` 和 `actor` 必须逐字匹配。有效期上限 180 秒；时钟容差与 V1 策略一致。
- 严格拒绝未知字段、重复 JSON 键、额外换行外的混合内容、非规范 Base64url、超长字段、重复 `jobId/nonce`、身份/仓库/路由不符。
- 返回 schema 为 `{version,jobId,operation,ok,observedAt,data,errorCode}`；`data` 严格固定字段、类型、范围和最大长度。错误仅返回预定枚举，不回显底层错误、响应正文、路径或 Secrets。
- 加密结果只发回独立的固定 V2 Issue；收件人一次性结果证书与本请求绑定，解密者检查完整 `jobId/operation`，不能把以前的结果用于新请求。

## 5. 权限与审批的关键区分

| 控制 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| 当前 ChatGPT 对话中展示请求并获得批准 | 用户在本对话表达了这一项意图 | 不能由 GitHub 服务器独立鉴别 |
| GitHub owner / Issue / event 核验 | 由指定已登录 GitHub 身份发表的指定密文评论 | 不能证明用户刚刚在 GPT 说过「批准」 |
| V2 固定操作枚举与零参数检查 | 消息不能携带任意 Shell、URL 或路径 | 不等于进程已获得完整沙箱隔离 |
| 最小权限主机账号与强制 SSH | SSH 身份只能运行固定只读采集器 | 不能排除采集器自身漏洞或 GitHub owner 账号被盗 |
| V1 双重关闭与独立发布锁 | 常规 V1 任意 Bash 请求和业务发布仍被拦截 | 不证明 V2 自动拥有执行权限 |

安全底线：V2 以后即便作为固定只读通道常态可用，**V1 任意 Bash 仍默认关闭**。如不能建立足够独立的授权和最小权限边界，应放弃常态主机访问，只使用 GitHub 连接器已有的只读数据。

## 6. 威胁模型与必须拒绝的输入

- 公开 Issue 中的非 owner 评论、被编辑的旧评论、fork/PR 事件、不同 repo/Issue、bot 身份伪造；
- 伪造的 `actor`、`target`、`jobId`、nonce、过期时间、其他字段、JSON 重复键、消息被转发到 V1；
- 企图传入 `command`、`path`、`url`、`headers`、`sql`、`pid`、`serviceName`、`env`、任意参数值或控制字符；
- 重放/并发同一请求、超大输入、循环触发、输出过长、超时、服务不可达、健康探针返回敏感 body，特别是 `/api/health/runtime` 的 `knowledgeRoot` 和 `activeProfiles` 泄露；
- 临时结果证书与任务不匹配、日志泄漏、异常信息回显、公开响应混入密钥或主机身份信息；
- V1 双开关被意外打开、发布锁被删除、主机采集账号被误授予 sudo 或容器管理权限。

## 7. 执行顺序与验收门禁

**阶段 A — 评审（当前允许）**

1. 本文在 Draft PR 评审；与 V1 技术说明核对边界，并确认为什么 CI 直读不需要任何主机通道。
2. 依据已核实的 `/api/health` 与 `/api/health/runtime` 源码，分别定义 liveness 和 readiness，不得误将硬编码 `UP` 作为端到端可用性；确认公网/本地路由与过滤前均返回 `unknown`。
3. 明确 V2 独立 SSH/GitHub 路由的安全边界和运维撤销流程。

**阶段 B — 离线实现（需下一次明确批准）**

4. 在新特性分支实现 exact-schema 解析、只读采集函数、脱敏输出、一次性认证/回环测试；不连接真实服务器。
5. 加入安全负例和 GitHub CI；仅交付 Draft PR，明确禁止 main 合并和生产发布。

**阶段 C — 真实主机试点（需要另一次单独批准）**

6. 安装独立只读账号/SSH 接入前，评审用户、路径、密钥、证书、命令强制和只读权限。
7. 先启用有期限的试点，再验证真实结果与强制拒绝，保留审计与可撤销证明。
8. **不得**启用 V1 通用 Shell、修改 `app/deploy/publication-hold.json`、触及生产数据库或自动合并。

**完成定义：** 用户从 ChatGPT 查询 GitHub CI 时可直接得到已验证结果；主机只读查询只有在单独批准试点、严格最小权限、真实加密回传、异常和安全拒绝用例全部通过后才能标记为可用。

## 8. 非目标

V2 不解决无人值守部署、重启服务、读写数据库、读取任意文件/日志、操作 PRP 业务数据、后台持续监控、通用 Shell 免授权、强身份签名的聊天批准或所有者账户被盗后的风险。此类能力必须单独立项。
