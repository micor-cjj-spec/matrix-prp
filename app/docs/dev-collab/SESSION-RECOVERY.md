# GPT 会话接管与持久化恢复（候选实现）

需求：[Issue #145](https://github.com/micor-cjj-spec/matrix-prp/issues/145)。代码在 Draft PR #138 内，**尚未进入 main 或进行真实生产级联调**。

## 会话不等于任务所有权

GitHub 的 `requirements/<REQ-ID>.json` 是任务状态的唯一权威来源，聊天历史不是。新会话应先调用只读索引查询、找到任务，并用最新的 Git SHA、PR、Issue 和可用断点还原工作。未写入 GitHub 的上下文、未推送提交、私有聊天内容不保证可以恢复。 `worker_id` 是建议性标识，不证明 ChatGPT 的真实会话身份；所有写入经所有者手动 GitHub Actions 及受审查环境执行。

## 推荐使用（只读）

从 `prp-collab-state` 分支的检出目录读取：

```bash
node app/scripts/dev-collab/recovery.mjs /tmp/prp-state/requirements
node app/scripts/dev-collab/recovery.mjs /tmp/prp-state/requirements REQ-20261031-001 T-003
```

全局索引只列出未完成需求和任务，展示状态、GitHub Issue、worker、断点时间与 PR。具体恢复报告包含最近断点的摘要、已完成成果、测试证据描述、阻塞、下一步、分支及 SHA。**该摘要不证明 SHA 已经存在、CI 已通过或旧会话已失效**；必须打开 GitHub 核对。

## 手动工作流：最多 10 个输入

协调器 Actions 是 owner-only、`main`-only、受 `prp-collab-controller` environment 审批控制的候选实现。新增唯一的 `recovery_payload` JSON 输入，保持 GitHub `workflow_dispatch` 总输入数量不超过 10 个。不要提交口令、Token、私钥、对话全文或敏感私人信息；状态分支位于公开仓库。

- `checkpoint`：原持有者通过 `worker_id`、`claim_id` 记录 `recovery_payload`：`{"summary":"Committed API implementation","next_step":"Review failing integration check","branch":"feat/task-api","head_sha":"<40位十六进制提交>","tests":"CI run #...","blockers":"...","pr_number":123}`。原有任务 SHA/PR 若有记录，必须匹配。
- `handoff`：原会话主动交接，`worker_id` 和 `claim_id` 必须为旧领取信息，`note` 是原因。payload：`{"new_worker_id":"chat-B","expected_version":5,"expected_head_sha":"<断点SHA>"}`。
- `takeover`：仅限 GitHub 仓库所有者对旧会话失效进行**显式手动批准**，需 `worker_id` 为旧持有者、`note` 为非空原因，payload：`{"new_worker_id":"chat-B","expected_version":5,"expected_claim_id":"<当前领取UUID>","expected_head_sha":"<断点SHA>"}`。旧会话不需要在线。无断点、状态版本过期、领取凭证不一致则拒绝。
- 同一次执行使用新的 `request_id` UUID；重试同一次执行才复用。记录经专用 App token 的 Git 非强制推送 CAS 落地后才认可成功。
- 新的 `claim_id` 与单调递增 `generation` 立即使旧领取失效，原任务进度、PR、提交 SHA 和审查状态均保留；任何旧凭证写入均拒绝。原任务仍在 IN_REVIEW 时，交接不代表代码获批，也不会自动合并。

**限制：** 现阶段未验证独立审查者审批和 GitHub App 真实生产式推送；发布冻结已在 main 生效，但不能用它替代授权。断点文字来自操作者，可能陈旧，必须以 Git 远端和 CI 证据为准。禁止因“会话长时间没有动静”自动接管。正式共享 V0 状态不作任何修改。

## Task assignment and non-production release sequencing

- [T-009 / Issue #146](https://github.com/micor-cjj-spec/matrix-prp/issues/146) contains four recovery-specific source/test files.
- T-001 owns `core.mjs`; T-003 owns the coordinator; T-004 owns this documentation; T-008 owns the real Git transaction stress test.
- [Draft state scope PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144) proposes the task DAG update. Do not direct-merge it into the protected state branch; only an explicitly reviewed dedicated App migration may apply it.
- Existing production publication hold in `main` has been verified, but this alone does **not** authorize merging [Draft code PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138) or running write commands.

## Emergency owner reconstruction when the original chat saved no checkpoint

If the former GPT chat died without writing a `checkpoint`, the owner can reconstruct a **minimal, explicitly owner-authored** checkpoint from existing GitHub evidence. Supply the same `takeover` action and its normal expected version/old-claim/SHA inputs, plus a `checkpoint` object in the JSON `recovery_payload`. It must contain a concise summary and next step, **an existing non-main feature branch name**, and the exact Git branch-head SHA, optionally a known matching PR number and tests. The trusted coordinator first confirms that GitHub-hosted owner/manual/workflow context is authentic, then runs `git ls-remote` against the checked-out repository's authenticated `origin`, requiring that branch's remote head equals the checkpoint SHA. Only then can the state machine reconstruct a checkpoint marked `origin=owner_verified_git` and transfer the old claim.

If there is no remote branch, if its head has changed, or if the old claim, version or trusted context differs, fail closed. A checkpoint summary is still human-authored and not proof of unseen chat activity or passing CI. This path never recovers unpushed commits and is not a license to force-push code. All actions remain in Draft PR #138 until separately approved and activated.
