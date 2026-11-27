# PRP Collaboration MVP：操作方式与安全边界

父需求：[Issue #132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)。
核心实现：[PR #271](https://github.com/micor-cjj-spec/matrix-prp/pull/271)（原候选 [#138](https://github.com/micor-cjj-spec/matrix-prp/pull/138)）。
状态迁移历史：[PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144)。
独立信任边界审查：[Issue #147](https://github.com/micor-cjj-spec/matrix-prp/issues/147)。
零点击操作要求：[Issue #148](https://github.com/micor-cjj-spec/matrix-prp/issues/148)。

## 当前状态与权威来源

截至 2026-11-27，协作自动入口已在受保护 main 上运行，V0→V1 迁移、专用 App 非强制 Git CAS 写入及脱敏回执均有真实证据。V1 指状态结构迁移后的九任务清单；业务状态版本随事务递增，不等于 schema_version。

以受保护分支 prp-collab-state 的 requirements/<REQ-ID>.json 及其精确 Git SHA 为唯一权威状态。Issue 描述、看板、历史手册、聊天记录均不是状态写入依据。验收基线 [V37](https://github.com/micor-cjj-spec/matrix-prp/blob/ff904968eb7860480fe0bbf3a0d9bd0892670069/requirements/REQ-20261031-001.json) 已有六项 DONE：T-001、T-002、T-003、T-006、T-007、T-009；其余任务继续以实时台账为准。V37 是历史证据，不是固定的 expected_version。

协作状态不是 PRP 生产数据库。仓库公开，禁止在状态文件、Issue、日志中保存私密聊天全文、Token、私钥、密码或个人敏感信息。生产发布冻结仍保留，协作验收不等于生产启用或部署。

## 日常操作：在 ChatGPT 中完成

日常入口为受保护 main 上的 .github/workflows/prp-collab-issue-ingress.yml，触发事件是 issues.opened。**版本边界：本手册所在 integration 基线 [cd8fb526](https://github.com/micor-cjj-spec/matrix-prp/tree/cd8fb52640bf7239d6bb77808549c8574bbe7351) 与实际运行的 main [3afa2acc](https://github.com/micor-cjj-spec/matrix-prp/tree/3afa2accb6e7a0f26a6a1dcadaa774aee1915210) 不同。** [integration 入口](https://github.com/micor-cjj-spec/matrix-prp/blob/cd8fb52640bf7239d6bb77808549c8574bbe7351/app/scripts/dev-collab/issue-ingress.mjs#L17-L40) 不支持 Owner Issue 自动 accept、capture_receipt、accept_receipt 或 accept_historical_*；其已实现的验收入口仍是受保护 main 上由 Owner 授权的手动 coordinator workflow_dispatch，参见 TRUSTED-ACCEPTANCE.md。本次文档 PR 不移植这些功能。以下日常事务及新版验收说明以明确标出的运行分支为准，执行前重新核验当前 main SHA 与实际入口；若入口不支持所需动作，停止并报告，禁止改用直接写状态等绕过方式。

1. 用户在 ChatGPT 中明确授权相应操作；ChatGPT 读取最新权威台账、状态 SHA、依赖及允许路径，核对 GitHub 连接的 Owner 身份。
2. 通过连接创建标题严格为 `[PRP-COLLAB-REQUEST]` 的 Owner Issue，正文仅为符合当前入口 schema 的 JSON。每笔新操作使用新 request_id（UUID）；同一操作的幂等重试保留原 request_id 和原始请求内容，不把已提交的请求修改成另一操作。
3. 受信任工作流验证原始事件、实时 Issue、作者、JSON schema、状态版本及专用 App 边界，通过非强制 Git CAS 更新状态分支。普通任务变更不能直接推送权威状态分支。
4. 同时核对 Actions 成功、脱敏回执与实际远端状态 SHA/版本/任务状态。Issue 创建或任务排队不代表事务成功。发现版本冲突，先读最新状态，确认前一请求未成功，才使用新的绑定发起新操作；不得盲目重试、强制推送或覆盖其他会话。

无需逐笔点击 GitHub Actions 或 Required reviewers。worker_id 是会话标签，不是独立身份认证；claim_id 是公开状态中的领取标识，不是秘密。真正身份由 GitHub Owner 事件认证，写入由专用 App 和现有事务控制。

## 任务执行、恢复及验收

- claim：依赖全部 DONE 且任务 READY 时领取；每次从最新状态读取 expected_version。
- start：使用当前领取的 claim_id 与 worker_id 启动。任务未成功进入 IN_PROGRESS 前，不将代码变更当作已启动的任务交付。
- 开发：基于最新受保护 integrate/<REQ-ID> 创建独立任务分支，只修改台账 allowed_paths 且不超过本次用户授权范围。使用精确 HEAD 的 Draft PR、完整 CI 和独立审查，禁止覆盖其他会话分支。
- progress / pause / block / resume / release：按已审查的入口和状态机执行；不得绕过版本、领取及依赖校验。
- checkpoint：保存简洁进度、下一步、远端分支及 HEAD、测试和阻塞信息；只在需要恢复时保存，不记录聊天全文或凭据。
- handoff / takeover：明确目标 worker_id，核验旧领取、当前版本、真实 Git 分支及 HEAD；轮换领取标识及 generation，拒绝旧领取。没有断点时按现有恢复机制核验真实远端证据；不能仅凭会话沉默自动抢占。参见 SESSION-RECOVERY.md 的恢复契约（其早期状态说明属于历史背景）。
- submit：绑定精确 PR 编号和 HEAD，事务成功才进入 IN_REVIEW；不等于 CI、合并或正式验收通过。
- accept（**仅已部署的新版 main**）：固定证据为 [main 3afa2acc 的入口](https://github.com/micor-cjj-spec/matrix-prp/blob/3afa2accb6e7a0f26a6a1dcadaa774aee1915210/app/scripts/dev-collab/issue-ingress.mjs#L18-L45) 与 [事务校验](https://github.com/micor-cjj-spec/matrix-prp/blob/3afa2accb6e7a0f26a6a1dcadaa774aee1915210/app/scripts/dev-collab/issue-transaction.mjs#L58-L83)。普通任务按现有普通验收契约核验文件范围、精确 HEAD、可信 CI、受保护 integration 中的合并证明及现行 Ruleset；必要时按该新版 main 的 capture_receipt / accept_receipt 契约保留合并前可信证据。旧 integration checkout 不接受这些 Owner Issue 动作，应遵循其已实现的手动 coordinator 验收契约。合并和正式 Accept 必须分别获得用户明确授权，不得因 CI 通过自行执行。
- accept_historical_415 / accept_historical_446 / accept_historical_271（**仅上述新版 main**）：只适用于该运行版本明确允许的历史任务及固定证据，绝不是通用绕过路径。当前历史 #271 验收仅覆盖 T-002、T-003、T-006；不得将其用于 T-004 或 T-008。
- close：不是普通 Owner Issue ingress 的允许操作；最终需求关闭仍须满足现有可信关闭契约、全部任务 DONE 及独立授权，不能把任务全部 DONE 等同于需求已关闭或生产发布。

不得自动合并 PR、扩大路径白名单、改变保护规则或执行生产部署。可信验收失败时保留 IN_REVIEW，检查具体证据缺口，不降低校验强度。

## 保护与安装边界（保持现有配置）

以下为现有安装和复核约束，而非重复启用或变更配置的指令：

1. 专用 Environment prp-collab-automation 限制 main；既有自动化入口不配置逐次 Required reviewers 或 Wait timer。旧 prp-collab-controller Environment 保持不变。
2. 私钥只保存在 Environment secret PRP_COLLAB_APP_PRIVATE_KEY；变量 PRP_COLLAB_APP_CLIENT_ID、PRP_COLLAB_APP_ID=5561446、PRP_COLLAB_RULESET_ID=26294671 按既有配置。不得将私钥或 Token 提供给 ChatGPT 或写入 Issue。
3. 专用 App 仅限 micor-cjj-spec/matrix-prp，自动入口请求单仓库 Contents: write；不授予 Administration 权限。
4. 保留状态分支 Ruleset #26294671（update、deletion、non_fast_forward，唯一 bypass 为专用 Integration App 5561446）、main Ruleset #24968649 和 integration Ruleset #28050327。协作 App 不得拥有 main bypass；integration 无 bypass 主体，依照现有必需检查和 PR 保护运行。
5. App 低权限 Token 可能无法读取完整 bypass_actors；必须在需要完整列表的现有验收路径中使用 Owner 可见证据并满足精确绑定及有效期，不能因列表不可见而视为空，也不能因此新增 App 权限。
6. 保留 app/deploy/publication-hold.json。协作验证仅涉及获准的状态分支及任务分支，不授权生产 SSH、SQL、数据库迁移或发布。

历史 V0→V1 迁移是固定的一次性事务，当前已完成。不得重复运行 migrate_v1，不把递增的业务版本解释为待迁移的 schema，不自动迁移任意版本。首次只读 probe 的历史回执仅证明读链路；后续真实事务才证明非强制写入。

## 新任务创建与登记

使用现有两步 Owner Issue 入口：先创建带唯一 PRP_TASK_MANIFEST 的 Task Issue，再通过 register_task 引用该 Issue，绑定最新状态版本、标题、依赖和允许路径。登记成功须有远端 CAS 回执，才可另行领取。普通新任务范围由 task-scope-policy.mjs 校验，不能将既有 bootstrap 任务的特殊路径授权推广给新任务；协作治理工作流、迁移、部署配置及信任根不属于普通新任务范围。参见 AUTO-REQUESTS.md 的请求格式，早期 V0 状态描述不作为当前运行依据。

## 只读看板与 Issue 投影

board.mjs 读取权威 JSON，显示状态、依赖、worker、PR 及精确状态 SHA，隐藏领取凭证和请求历史。现有 PRP Collaboration Board 工作流仅通过 workflow_dispatch 在 main 运行，权限为 contents: read。当前连接器不一定提供 dispatch；直接读取权威 JSON 仍可核查当前状态，但不能冒充真实 Board 运行回执。

Issue 投影与 Board、Owner 请求回执是不同操作。真实 Issue 投影写入必须独立获准；不得因为 Accept 或只读看板通过而自动启用投影。Issue 投影始终不是权威任务状态。

## 回归与真实验收证据

以下为已经核验的历史证据，不是本次候选 HEAD 的新测试回执：

| 场景 | 既有证据及限制 |
| --- | --- |
| 双会话竞争、重复领取、主动交接及失联接管 | V37 台账保留 T-001/T-002 的 V2–V10 真实事务和归档断点；重复领取拒绝记录见 T-001 归档 checkpoint。不能将其说成重新执行了真实 workflow_dispatch 并发试验。 |
| CAS、幂等、防重放、依赖及权限边界 | [PR #492 专项流水线](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45839129899) 344/344 PASS，含真实本地隔离裸 Git 竞态测试；不是线上并发写入实验。 |
| 真实 Owner 授权、专用 App 写入及历史证据验收 | [T-006 Owner Issue #496](https://github.com/micor-cjj-spec/matrix-prp/issues/496#issuecomment-7207348200)、[Actions #45922806139](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45922806139)、[V37](https://github.com/micor-cjj-spec/matrix-prp/blob/ff904968eb7860480fe0bbf3a0d9bd0892670069/requirements/REQ-20261031-001.json) 一致，非强制 CAS 晋升成功。 |
| 看板 | [真实 V33 Board](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45805618945) 成功；T-006 经 Owner 明确接受复用及源码一致性、专项测试证据，未在 V36 重新 dispatch，也未真实写入 Issue 投影。 |
| 完整 CI | [#492 合并后 main CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45840881851) 34/34 PASS；新任务仍须按其当前基线和精确 HEAD 检查全部 CI、影响分析、协作契约及审查。 |

已有真实试点可复用；不因文档更新而重复开展实际写入竞态、部署或扩展治理。对候选 HEAD 的测试与历史证据分开记录，不把 CI 通过等同于实际生产能力、独立审查或正式验收。

## 验证命令（本地或现有 CI）

```bash
node --test app/scripts/dev-collab/*.test.mjs
bash -n app/scripts/dev-collab/state-transaction.sh
```

完整 CI、Feature Impact Report、PRP Dev Collaboration Contract 均使用现有工作流。核对精确 PR HEAD、基线、变更文件、完整检查、审查回执及生产隔离；真实状态变更须核对 Owner Issue、Actions 和权威台账三方证据。禁止因手册更新而改变实际权限、校验机制或发布门禁。
