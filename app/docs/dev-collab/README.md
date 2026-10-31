# Matrix PRP cross-session development collaboration — MVP v1

Parent requirement: [REQ-20261031-001 / #132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)

## Source of truth and safety

- A requirement owns tasks; chat conversations are transient workers.
- One root GitHub Issue represents the requirement; individual Issues represent tasks.
- The intended authoritative state is a protected, independently controlled `prp-collab-state` Git ref containing `requirements/<REQ-ID>.json`. Issue titles, checkboxes and labels are projections, not mutexes.
- `main` stays protected. Never automatically merge, deploy, run SSH, use production DB/Keycloak or install MCP as part of the coordination workflow.
- Current review branch includes the pure contract, templates, owner-only manual workflow coordinator, Git fast-forward state transactions and local-Git concurrency tests. The `prp-collab-state` branch has been seeded with `REQ-20261031-001` at version 0. **The coordinator is NOT active on protected main.** Claims become operational only after separate review, protected state-ref authorization and approved activation.
- The existing `.github/workflows/codex-prp-worker.yml` is manual-only and currently opens review PRs against `main`. Do not assume it targets a requirement integration branch or allows arbitrary directories. Adapt separately.

## Task status and lifecycle

`READY -> CLAIMED -> IN_PROGRESS -> IN_REVIEW -> DONE` is the normal path.
`IN_PROGRESS -> BLOCKED/PAUSED -> IN_PROGRESS` and `CLAIMED/IN_PROGRESS/BLOCKED/PAUSED -> READY` on release are supported. Task `DONE` requires independent reviewer authorization, verified CI and verified integration merge. Requirement `CLOSED` requires explicit acceptance and every task to be DONE/CANCELED. No chat message alone updates authoritative state.

## Cross-session behavior

1. Any new conversation reads the parent Issue, linked tasks and current state version before acting.
2. A conversation requests a claim with GitHub-authenticated actor, `worker_id`, task ID and unique UUID `request_id`.
3. The coordinator must validate ownership, dependency DAG, write-path overlap, and optimistic Git non-fast-forward update. It returns an opaque `claim_id`.
4. Only operations presenting the latest claim ID plus the same authenticated GitHub actor/worker may update a claimed task. `worker_id` is advisory; it is not a credential.
5. Worker commits on an isolated branch and records PR, commit SHA and CI evidence. It cannot self-approve.
6. New sessions use the latest recorded state and linked artifacts, not ChatGPT memory alone.

## Implementation and permission boundaries

The pure `core.mjs` module implements dependency validation, path reservation, state transitions, idempotent command receipts and fail-closed approval requirements. This is accompanied by a manual-only GitHub Actions transaction runner, which uses re-fetch, non-force Git push and bounded retries. Local bare-Git concurrent process tests are included. Verified reviewer/CI acceptance and automatic Issue reconciliation are **not implemented**; coordinator cannot invoke `accept` or `close`. No user-provided Issue content may execute as shell commands.

## Start and acceptance checks

Run locally from the repo root:

```bash
node --test app/scripts/dev-collab/*.test.mjs
```

Before a real multi-session acceptance, verify two simultaneous claims for the same task lead to one winner, independent tasks can both progress, duplicate request IDs are idempotent, stale claims fail, issue projection failures can be reconciled, unauthorized users fail closed, and no production deployment occurs.

## Planned work items

- T-001 #133 contract/tests (Draft PR #138; awaiting acceptance)
- T-002 #134 Issue/PR templates (Draft PR #138; awaiting acceptance)
- T-003 #135 trusted workflow coordinator and atomic Git state writes (Draft PR #138; not active on main)
- T-004 #136 cross-process/test fixtures and operating guide (Draft PR #138; acceptance pending)
- T-005 #137 integration acceptance (not started)

The state request history is deliberately bounded at 512 entries per requirement and fails closed when full; archival/re-keying requires a separately reviewed protocol change. A PR being green is evidence of tests passing; it is not evidence that live coordination, OAuth or production release has occurred.

## Current activation blocker

`prp-collab-state` is currently **unprotected** on GitHub. The candidate write coordinator refuses to run until branch protection is enabled and independently reviewed. The optional read-only board workflow has no write token and does not require activation of the write path. Do not regard feature-branch CI success as permission to merge or enable production release.

> Security activation change: the write coordinator requires a reviewed dedicated GitHub App, an environment approval and an exact active state-ref ruleset. The default Actions token no longer has contents write. The secrets, GitHub App and branch ruleset have not been provisioned.
