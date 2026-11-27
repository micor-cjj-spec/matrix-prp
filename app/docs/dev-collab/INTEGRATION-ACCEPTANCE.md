# REQ-20261031-001 总体集成验收记录（T-005）

日期：2026-11-27。范围：受保护 integration 基线的集成审查与证据汇总。本文是待审交付物，不是状态写入、最终需求关闭、主线晋升或生产发布授权。

## 1. 精确基线及验收状态

- [Integration 基线](https://github.com/micor-cjj-spec/matrix-prp/tree/8785c72e17b225832fa5356e72f97e3d948d1182)：`8785c72e17b225832fa5356e72f97e3d948d1182`，包含 T-008 的真实 Merge Commit。
- [权威台账 V45](https://github.com/micor-cjj-spec/matrix-prp/blob/7fd506ab58ce9b88e66246ad47a295e1e8d76383/requirements/REQ-20261031-001.json)：八项依赖 DONE，T-005 READY；本次真实 Claim [#514](https://github.com/micor-cjj-spec/matrix-prp/issues/514#issuecomment-7209431250) 晋升 V46，Start [#516](https://github.com/micor-cjj-spec/matrix-prp/issues/516#issuecomment-7209451166) 晋升 V47（[精确台账](https://github.com/micor-cjj-spec/matrix-prp/blob/bf1db2450b2892d47332860350058c6c97b5298b/requirements/REQ-20261031-001.json)），T-005 IN_PROGRESS，需求 ACTIVE。
- 唯一授权路径：本文件。八项依赖及其领取锁不再修改。状态分支、main/dev、真实 Issue 投影及部署均不在本次交付范围内。
- 实际运行的 main 是 `3afa2accb6e7a0f26a6a1dcadaa774aee1915210`；dev 是 `353b939e41f21a98d2101fcb5e9796cbb34888bc`。两条分支均未被本任务修改。

## 2. 八项已正式验收任务

以下 ACCEPT 版本和请求 ID 来自 V45 的 processed_requests。PR 是各任务绑定的交付证据；历史 #271 的三项验收使用已批准的历史专用入口，不是新提交或重复验收。表中合并提交均经 GitHub 比较核实为上述 integration 基线的祖先（T-008 自身等于基线）。

| 任务 | 绑定 PR | 合并 SHA | 正式验收版本 | 验收请求 ID |
| --- | --- | --- | --- | --- |
| T-001 状态模型与 CAS 核心 | [#415](https://github.com/micor-cjj-spec/matrix-prp/pull/415) | `5a30345529a1d07819069822a1b90e07b5376fcc` | V17 | `9169f7c3-0d01-4433-8f8b-03ccb2f361a4` |
| T-002 任务及 PR 模板 | [#271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) | `3177009eeb692c766715ba0c6e1133844f469981` | V29 | `ac022026-1126-4a02-8504-9f058df59bdd` |
| T-003 协调器和 Actions | [#271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) | `3177009eeb692c766715ba0c6e1133844f469981` | V33 | `ac032026-1126-4a03-8504-6ce4df0222ac` |
| T-004 操作手册及回归 | [#500](https://github.com/micor-cjj-spec/matrix-prp/pull/500) | `1f590ece3a1142ca6d349148cfb08a20d396116f` | V41 | `d4040005-1127-4a04-8601-000000000005` |
| T-006 看板及可选投影 | [#271](https://github.com/micor-cjj-spec/matrix-prp/pull/271) | `3177009eeb692c766715ba0c6e1133844f469981` | V37 | `d6060004-1127-4a06-8601-000000000004` |
| T-007 可信验收及 App 安全 | [#446](https://github.com/micor-cjj-spec/matrix-prp/pull/446) | `22b477fc52e90b25663ecb911e280d2979018d53` | V21 | `c34cc2f8-f73b-4d48-84c9-38951ac14c46` |
| T-008 真实隔离 Git 竞态及边界 | [#509](https://github.com/micor-cjj-spec/matrix-prp/pull/509) | `8785c72e17b225832fa5356e72f97e3d948d1182` | V45 | `d4080005-1127-4a08-8601-000000000005` |
| T-009 会话恢复及接管 | [#461](https://github.com/micor-cjj-spec/matrix-prp/pull/461) | `cd8fb52640bf7239d6bb77808549c8574bbe7351` | V25 | `ac092026-1126-4a09-8501-cd8fb52640bf` |

V45 任务记录含精确 PR HEAD 与已释放的 claim；T-004、T-008 的 [#505](https://github.com/micor-cjj-spec/matrix-prp/issues/505#issuecomment-7208149915)、[#513](https://github.com/micor-cjj-spec/matrix-prp/issues/513#issuecomment-7209280289) 分别证明正式验收。V45 另保留 T-004、T-008、T-009 的合并前持久化回执。历史任务不要求伪造这种新式回执。

## 3. 端到端证据矩阵

| 验收目标 | 已核实证据与边界 |
| --- | --- |
| 权威状态、原子领取和依赖 | V45 的实际事务 V2–V10 记录 T-001/T-002 领取、checkpoint、handoff、release、重新领取、takeover；重复领取拒绝的历史归档断点见 [OPERATIONS.md](./OPERATIONS.md)。本次 T-005 Claim/Start 又经真实 Owner Issue、专用 App、非强制 Git CAS 成功写入；不是重新开展线上双会话竞态。 |
| 并发和幂等 | [历史 #492 专项](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45839129899) 344/344 PASS，含真实本地隔离裸 Git 竞争、幂等、非重叠任务及恢复测试；[T-008 integration 专项](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45931233043) 233/233 PASS，新增发布条件完整表达式和负向变异验证。前者与后者属于不同源码基线，不把测试数量合并或混称。 |
| 端到端授权、验收和恢复 | V17–V45 八项正式 accept 的非强制事务回执，T-009 接管恢复任务已 DONE；真实 Owner Issue 与保护分支状态一致。历史试点复用，未新增真实竞态、接管或失联测试。 |
| 看板及投影 | [V33 只读 Board 实测](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45805618945) success；[T-006 V37 回执](https://github.com/micor-cjj-spec/matrix-prp/issues/496#issuecomment-7207348200) 正式验收。投影仅可选、手动、非权威，复用已有离线测试；未执行真实投影写入，不声称看板实时推送或线上投影验收。 |
| CI、审查和 Tree | [T-008 CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45931233041) 34/34 PASS（一次失败任务重试），[专项](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45931233043) 233/233 PASS，[Impact](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45931233049) PASS，[独立复审](https://github.com/micor-cjj-spec/matrix-prp/pull/509#issuecomment-7208582706) 无发现；[可信回执 #512](https://github.com/micor-cjj-spec/matrix-prp/issues/512#issuecomment-7208809889) 于真实合并前持久化，合并 Tree `a33f617793836e8a883d73f25c3c2ccb8e3d3072` 与已测试 Tree 相同。 |
| 生产隔离 | 本次读取的 main 发布锁仍存在；[历史 main CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45840881851) 34/34 PASS；[历史发布锁实测](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/43355995634) publish skipped（参见历史 readiness 文档）。当前 integration 无生产 push 触发，T-008 已验收边界。不是重新部署或重新运行生产检查。 |

## 4. 安全边界与版本差异

核验现有 Ruleset：main #24968649 active、无 bypass；integration #28050327 active、无 bypass，Merge Commit、七项必需检查、审查线程解决；状态分支 #26294671 active、唯一 bypass 为既有专用 Integration App 5561446，并禁止删除和非快进。未改变任何规则或权限。生产 hold 保留；此报告不批准真实 Issue 投影、SSH、SQL、迁移、main/dev 合并或发布。

**重要残余事项：integration 并不等于已运行的 main。** 本次 GitHub compare 显示相对当前 main 的 integration 有 21 个独有提交、main 有 10 个独有提交（diverged）。例如 integration 的 issue-ingress.mjs Blob `eae7fc5ac62f4fe1617a30a1176f26fe6a92de2e` 不含新版自动验收动作，而运行 main 的 Blob `91396d9b244fd0169b39fae3c60ba0bdd21d9cbb` 支持 capture_receipt / accept_receipt / 特定历史入口。参见 [OPERATIONS.md](./OPERATIONS.md) 的版本边界。历史真实运行验证以实际 main 为准；本次 integration 候选验收以其精确 Tree 为准，不移植或回退主线代码。不把文档交付等同最终主线兼容性验收。历史 #138 仍为未合并 Draft 候选，不作为最终晋升 PR。

## 5. 本次交付待核验与结论

八项正式依赖已齐备，历史真实证据可复用，基线合并链及生产隔离满足本次集成审查范围。本报告仅新增一个授权文档，新的 Draft PR 需对其精确 HEAD 与受保护 integration 基线执行完整 CI（34 项现有 CI 任务）、Feature Impact、PRP Dev Collaboration Contract、独立审查。报告提交时不预先声称这些新检查成功；成功凭据应以实际 PR、Actions 和审查回执为准，不为填入自身 HEAD 而反复更新文件。

当前 T-005 IN_PROGRESS、需求 ACTIVE。后续 Submit、合并前回执保存、integration Merge Commit、正式 Accept 分别遵循现有机制及明确授权。即使 T-005 DONE，也不等于需求 CLOSED；最终主线集成需独立授权、核验 main 最新基线和兼容性、完整 CI 与可信验收，并依据实际运行版本的现有 close 门禁另行决定。生产发布锁保持，不在本任务内解除。若发生证据冲突、源码版本变化、权限或 CI 问题，按已有门禁停止，不直接写入状态，不绕过。
