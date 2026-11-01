# Protected V0→V1 task-state migration — Draft plan

Source: [Draft PR #138](https://github.com/micor-cjj-spec/matrix-prp/pull/138), state proposal [Draft PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144), tracking [#139](https://github.com/micor-cjj-spec/matrix-prp/issues/139).

**This workflow is not on main. No state migration was executed.** Owner approval to keep developing this code is not approval to merge or run a live migration.

## Read-only preview

The manual `PRP Collaboration State Migration` workflow accepts `mode=verify`, `expected_state_sha`, and `expected_proposal_sha`. The initial values are:

- State V0: `062036f7021e215ffbfdcbf5689d207a0549b68b`
- Draft proposal: `fb57656dca6df5f12e083fc0430263b4d88e452d`

Verification is owner-only, main-only and environment-gated. It uses the default read-only token; it **does not mint** the writer App token, make commits or push any ref.

It checks both immutable SHA pins against current remote branch heads, Git ancestry, that the only changed file is `requirements/REQ-20261031-001.json`, PR #144's base/head/repository and exact file list, the active state Ruleset and sole App bypass, and the complete strictly specified 5→9 task delta. Existing statuses, claims and request ledger must remain unchanged. Every unexpected field, path, dependency or historical task state is rejected.

## One-shot apply (requires separate explicit authorization)

After independent review of the migration source and proposal and a separately approved merge of **the migration source** to main, the owner may mark PR #144 *Ready for review* and request explicit approval for the exact SHAs. Only then use `mode=apply` and type `APPLY-REQ-20261031-001-V1`. The protected environment reviewer must approve before the job can use the dedicated GitHub App token. It verifies the App installation token is scoped to exactly this one repo.

Immediately before the push the job rechecks the remote state and proposal heads. It stages **only the requirement JSON**, commits with GitHub run/PR/SHA audit metadata, then attempts one non-force App-token push to `prp-collab-state`. If anything has drifted or permission denies the push, it fails without force or retry. The result is considered applied **only after** the remote Git push succeeds and the new protected state SHA is independently verified.

The migration does not merge PR #144, merge the bootstrap PR #138, update production data, release any claims, approve tasks, or remove the production publication hold. The three CI workflow governance files remain outside ordinary task scopes.

**Important:** environment reviewer and App installation behavior must be demonstrated live. Passing CI in a Draft PR does not establish that the write path is active.
