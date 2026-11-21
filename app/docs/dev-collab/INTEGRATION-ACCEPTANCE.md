# REQ-20261031-001 · T-005 集成验收证据登记（审查草案）

> **NO-GO / 未验收 / 不得标记 DONE**。本文件仅是 T-005 的候选验收清单，不是权限批准、已执行的测试记录、真实双会话验收或任务完成证明。
>
> 证据快照：2026-11-21；PR 和 CI 状态会变化。任何签收、合并或写入之前必须重新读取 GitHub 当前 head SHA、全部 required checks、审查意见、权威状态分支与 Ruleset。
>
> 父需求 [#132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)；T-005 [#137](https://github.com/micor-cjj-spec/matrix-prp/issues/137)；状态迁移提案 [#144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)。

## 1. 权威状态与绝对禁止事项

- 权威分支：**prp-collab-state**，路径 **requirements/REQ-20261031-001.json**，2026-11-21 核查为 **V0 / ACTIVE / 5 个 READY / 0 claim**。权威状态不是 PRP 生产数据库。
- V1 候选为 Draft [#144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)，提案 head **bf80d5c384d5f687cb980b6e04127fc42167d7a8**，仅变更上述一个 JSON 文件。它尚未合并，也尚未通过受保护的 GitHub App 迁移。
- 不得把尚处于 Draft 的独立任务 PR 或 bootstrap PR 当作任务接受证明；不可更改 READY/claim、回写 DONE、执行 V0→V1、绕过分支保护或发起真实写入 pilot。
- **main** 保持 **app/deploy/publication-hold.json**；协作开发的验收不授予任何生产发布、MCP/Keycloak 变更、数据库迁移或解除发布冻结的权限。
- T-005 候选文件白名单只有本文件，不应加入源代码、workflow、secret、部署配置或其它任务的文档。

## 2. 单任务候选及范围对账

以下都是**代码审查候选**，不是正式接受或 DONE。每一项的 exact SHA 必须在其 PR 基准分支无意外漂移时重新核验。

| 范围 | PR / head SHA（快照） | GitHub 差异核查 | 接受状态 |
| --- | --- | --- | --- |
| T-001 状态引擎 | [#211](https://github.com/micor-cjj-spec/matrix-prp/pull/211) / 0b771dc16140b0011fb6bd03d37b44104ea65d02 | 2 文件；`core.mjs` 与总候选存在已识别差异，需 #245 集成桥接 | 未接受 |
| T-002 Issue/PR 模板 | [#210](https://github.com/micor-cjj-spec/matrix-prp/pull/210) / 604466dbaa368638708d4a24b5b553a310b607d0 | 3 个文件，早期静态审计 | 未接受 |
| T-007 安全验收模块 | [#226](https://github.com/micor-cjj-spec/matrix-prp/pull/226) / 079cf863e70a8004e3fb4dd50ffd7d4828864c93 | 12/12 精确白名单 | 未接受 |
| T-009 恢复/接管 | [#227](https://github.com/micor-cjj-spec/matrix-prp/pull/227) / 72b795a70ad15d457272717fad4c3477cb23bbb1 | 4/4 精确白名单 | 未接受 |
| T-003 协调器 | [#230](https://github.com/micor-cjj-spec/matrix-prp/pull/230) / 21321a27efd3b83f41ec3fa3d380f116a9ac0158 | 3/3 白名单；模块依赖已存在 | 未接受 |
| T-004 回归测试与手册 | [#233](https://github.com/micor-cjj-spec/matrix-prp/pull/233) / 7d9c9b2030126b8f476e4a9e165bf253202fd0f1 | 12 个文件，无额外范围 | 未接受 |
| T-006 看板与 Issue 投影 | [#234](https://github.com/micor-cjj-spec/matrix-prp/pull/234) / 2d804a37cbbb416b2695ee50a433a633649c1aa7 | 9/9 精确白名单 | 未接受 |
| T-008 CAS/工作流测试 | [#237](https://github.com/micor-cjj-spec/matrix-prp/pull/237) / 9b6afe0c4b4d24b0e58dedf94dbd2852a31a8058 | 5/5 精确白名单 | 未接受 |
| 17 个 bootstrap 信任根文件（不是普通 T 任务） | [#236](https://github.com/micor-cjj-spec/matrix-prp/pull/236) / 8378d3dc28ffa4b2c9875d405d323abd34452733 | 17 个独立文件；0 个与任务白名单交叉 | 独立安全审查待完成 |

**2026-11-21 独立 PR / 总候选 blob 对账：** 在 T-001～T-004、T-006～T-009 的 50 个候选任务文件中，49 个与 #138 对应 blob 完全一致；仅 T-001 的 `core.mjs` 存在内置路径校验 vs 引用独立治理模块的结构差异。这个差异属于跨任务/治理集成边界，不能隐式覆盖 T-001 的两文件候选。已建立 [仅供集成审查的 Draft #245](https://github.com/micor-cjj-spec/matrix-prp/pull/245)，确切 head `eb001ea56a9da1fc6c38851770bc58b6749aa053`，在含治理模块的 [#236](https://github.com/micor-cjj-spec/matrix-prp/pull/236) 之上**只变更 1 个 `core.mjs` 文件**，使其 blob 与 #138 一致。两份路径安全规则的人工源码核查相近，但无独立运行时等价证据；**#245 不是普通工作任务 PR，也不意味着 T-001 被接受**。正式集成须显式审核此桥接及高权限治理依赖，不得将跨 scope 变更混入普通 worker 提交。

任务依赖按 [#144](https://github.com/micor-cjj-spec/matrix-prp/pull/144) 的候选图核对：T-007 → T-001；T-009 → T-001/T-007；T-003 → T-001/T-007/T-009；T-004、T-006、T-008 后继；T-005 必须在其它八项都经过正式验收后才能处理。**代码堆叠关系不等于 GitHub 受保护集成分支的实际合并证据。**

## 3. CI 与复现证据（严格区分来源）

| 来源和确切 head | 观察到的证据 | 对 T-005 的结论 |
| --- | --- | --- |
| 源候选 [#138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)，8fdd189e26a7b5b044b0b98efef22c7812bd54bc | [协作契约 #44901620609](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44901620609) **178/178 成功**；[Feature Impact #44901620559](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44901620559) 成功；[完整 CI #44901620594](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44901620594) **32/34，失败 2 个临时 Keycloak PKCE E2E** | **NO-GO**，不可用绿色子集替代全绿 |
| 独立测试环境修复 [#213](https://github.com/micor-cjj-spec/matrix-prp/pull/213)，c2a468359ffd623b46a39b3c06d66aad485b01ac | [CI #44434350947](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44434350947) 在其自身 head **34/34 成功**；仅两个测试环境文件 | 不能证明已集成源代码成功 |
| 组合验证 [#240](https://github.com/micor-cjj-spec/matrix-prp/pull/240)，8a3c04cef545c15a5fa1c88e9cd2163f7311e753 | 在 #138 后叠加 #213 的两个确切 blob；GitHub compare 仅新增 2 个文件改动；[CI #44907308326](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44907308326)、[契约 #44907308220](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44907308220)、[Impact #44907308239](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44907308239) 已触发，**第一次运行已结束：33/34 成功，仅 Chromium E2E 失败；对应 Job 在 Maven 打包阶段提前退出，详细构建日志未进入 Actions 输出；已对该失败 Job 发起第 2 次重试，当前仍排队中** | **待结果**；此组合 PR 也不是可直接合并的任务 PR |

不可把 #138、#213 或其它分支的绿色结果套用到 #240 或未来的受保护集成分支。必须在目标 exact head 重新检查 required CI、状态与可信 workflow provenance。

## 4. 待完成的强制门禁（全部未打勾）

- [ ] **G1 · source review**：每个任务 PR 的真实 diff / base / head / allowed_paths / rename 路径经过独立审查；源变更只进入已批准的受保护 **integrate/REQ-20261031-001** 分支，不能未经授权合并 main。
- [ ] **G2 · privileged security**：独立审查 #236 的 17 个治理文件、Issue 来源和重读校验、App 令牌最小权限、Ruleset/Environment、迁移精确 SHA、身份伪造和回放/CAS 攻击；安全审查 Issue [#147](https://github.com/micor-cjj-spec/matrix-prp/issues/147) 未关闭。
- [ ] **G3 · full CI**：组合候选及最终集成 exact-head 的全部 required checks 成功；PKCE readonly/crud 都通过，不能放宽 TLS/认证、跳过失败测试或伪造状态。
- [ ] **G4 · protected integration**：受保护集成分支存在且 Ruleset 已由可信 GitHub API 核验；逐个任务仅合并独立白名单 PR；成功之后才有资格进入可信 accept 复核，任何工作流不能自行宣告 DONE。
- [ ] **G5 · Environment / App**：管理员只读检查 **prp-collab-automation** 的密钥和变量是否存在（不读取密钥内容）、无 Required reviewers/wait timer、部署分支仅 main，单仓库安装 App 和真实 Ruleset bypass。配置未经实际验证不得视作完成。
- [ ] **G6 · owner-authorized bootstrap merge + read-only probe**：源代码经明确授权合并到受保护 main 后，实际 owner Issue opened 只读 probe 成功；验证脱敏回执、未写保护状态、旧 V0 SHA 完全不变。
- [ ] **G7 · independently reviewed migration**：所有者明确授权特定 V0→V1；#144 离开 Draft 并取得**非所有者真实协作者对确切提案 head 的 APPROVED 审查**；限定的 GitHub App 非强制推送成功并核对新状态 SHA。普通“继续”不是迁移指令。
- [ ] **G8 · two-session real pilot**：两个独立 ChatGPT 会话在同一 V1 状态操作；不同任务先以同一 version 竞争并证明一方 stale 被拒、重读后成功；同任务重叠领取被拒；主动交接 / 旧 claim 失效 / 授权接管 / 幂等 UUID / 脱敏回执均由真实 Issue、Actions、远端 Git SHA 证明。
- [ ] **G9 · final trusted accept / close**：全部前置任务均真实 DONE；T-005 独立 reviewer 检查精确 PR 和 CI 证据、合并 SHA、状态版本与所有者决策后才可触发受信任验收，普通 owner Issue ingress 不提供 accept / close。
- [ ] **G10 · release separation**：明确记录所有本次测试、迁移、状态更新与 PR merge 均不授权生产发布；publication hold 必须持续保留，解除需另一独立明确授权。

## 5. 必须补齐的验收记录

完成某项门禁时，记录真实 GitHub 证据而不是填“已测试”：

| 字段 | 必要证据 | 当前 |
| --- | --- | --- |
| integration branch / protected Ruleset | 精确分支、Ruleset ID、被保护状态和验证时间 | **未验证** |
| task PR → trusted merge | PR #、submitted head SHA、target branch、merge SHA、required checks、reviewer | **未验证** |
| #240 combined CI | 3 个 workflow 的完成状态和准确 Job 成败、最终 head SHA | **33/34，Chromium 单项重试排队；完整 CI 尚未全绿** |
| real owner Issue probe | Issue #、run ID、App installation 范围、V0 前后 SHA | **未执行** |
| pinned V0→V1 migration | 明确 owner 授权、独立 reviewer、提案/旧/新 SHA、App receipt | **未授权／未执行** |
| two conversations / collision recovery | 每次 request UUID、run ID、成功或拒绝原因、状态版本、远端 SHA | **未执行** |
| task acceptance / requirement close | 可信 reviewer、独立审查证据、具体 task status / state SHA | **未执行** |

### 验收结论

**NO-GO。T-005 未领取、未提交、未接受、未完成。** 目前只允许继续 Draft 审查、隔离测试和收集可信只读证据。任何改变受保护状态、任务完成标记、合并主干、授权 App 写入或解除生产发布冻结，都必须经过其各自明确授权和正式门禁。
