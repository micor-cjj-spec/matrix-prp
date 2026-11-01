# Bootstrap PR reconciliation — REQ-20261031-001

The current Draft PR #138 was built **before** live cross-chat claiming was activated. The authoritative `prp-collab-state` snapshot remains version 0 with no claims, and PR #138 targets `main`, not the planned `integrate/REQ-20261031-001` branch. The existing task acceptance policy **must not** retroactively treat this bootstrap PR as five independently claimed, checked and accepted task PRs.

An audit of the actual 39 changed files in PR #138 against the original five task scopes, performed on 2026-11-01, found **14 assigned files** (T-001 2, T-002 3, T-003 3, T-004 6, T-005 0) and **25 unassigned files**. A current audit should always be generated from live GitHub data rather than trusting these historical counts.

Read-only reproducible audit:

```sh
gh api repos/micor-cjj-spec/matrix-prp/pulls/138 > /tmp/prp-bootstrap-pr.json
gh api 'repos/micor-cjj-spec/matrix-prp/pulls/138/files?per_page=100' > /tmp/prp-bootstrap-files.json
gh api 'repos/micor-cjj-spec/matrix-prp/contents/requirements/REQ-20261031-001.json?ref=prp-collab-state' --jq '.content' | base64 -d > /tmp/prp-bootstrap-state.json
node app/scripts/dev-collab/bootstrap-audit.mjs /tmp/prp-bootstrap-state.json /tmp/prp-bootstrap-pr.json /tmp/prp-bootstrap-files.json
```

The audit never modifies GitHub refs, issues, state, PRs or servers. It rejects truncated or duplicate file evidence.

## Required reconciliation before pilot activation

1. Independently review PR #138 as an **initial bootstrap implementation**, keeping it Draft. Do not merge to `main` without separately assessing the existing production deployment workflow and explicitly approving any release impact.
2. Allocate the 25 additional files to reviewed work packages (status board/projection, evidence+security verifier, CI+governance), using narrow path ownership, and publish the resulting requirement/task manifest through a **separate approved state migration**. Do not silently append tasks or overwrite state V0 through an ordinary unprotected Git push.
3. Provision the dedicated GitHub App, reviewer environment, and exact protected state Ruleset; independently verify the app write path and all blocking permissions.
4. Prepare an independent, protected integration branch and task-specific development PRs. Each new task PR must have a submitted head SHA, a true PR CI result, the allowed files and an owner-authorized acceptance workflow.
5. Start the first real `claim` from a fresh requirement or explicitly approved continuation. Do not alter historical task statuses as a substitute for live evidence.

**No production merge, GitHub App installation, Ruleset creation, environment mutation, task claiming, or task acceptance is performed by this audit or documentation.**

**Important:** `matches_integration_pr_shape` is only structural evidence. The offline audit always returns `task_acceptance_verified: false`; only the trusted owner-triggered live verifier can establish CI provenance, merge ancestry, task write scope, and final approval.

## Protected state V0→V1 migration candidate (2026-11-01)

The concrete proposal is [Draft PR #144](https://github.com/micor-cjj-spec/matrix-prp/pull/144), **against `prp-collab-state`**, not main. It preserves all five tasks' READY/null-claim state and adds [T-006 / #141](https://github.com/micor-cjj-spec/matrix-prp/issues/141) with 9 paths, [T-007 / #142](https://github.com/micor-cjj-spec/matrix-prp/issues/142) with 12 paths, and [T-008 / #143](https://github.com/micor-cjj-spec/matrix-prp/issues/143) with 5 paths. It gives T-005 one future integration acceptance artifact, replacing the former impossible empty allowlist.

The scope proposal validator `verifyScopeMigrationProposal` compares old and candidate snapshots, checks exact task scopes and issues, unchanged historic task states, approved dependencies, zero processed requests and the sole sequential T-004/T-005 document-path overlap. Its result is only `structurally_valid`: **it never authorizes the state write or certifies task acceptance**. Three critical CI workflow files remain bootstrap-governance-only and must not enter ordinary task scopes.

PR #144 cannot be merged as an ordinary maintainer PR because the live state branch Ruleset requires the dedicated GitHub App bypass. The coordinator still has no audited `migrate` action; configure and separately approve a protected migration mechanism before considering application. Do not force-push, bypass the Ruleset or mark any task DONE to make the merge possible.
