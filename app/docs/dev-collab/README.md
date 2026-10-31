# Matrix PRP cross-session development collaboration — MVP v1

Parent requirement: [REQ-20261031-001 / #132](https://github.com/micor-cjj-spec/matrix-prp/issues/132)

## Source of truth and safety

- A requirement owns tasks; chat conversations are transient workers.
- One root GitHub Issue represents the requirement; individual Issues represent tasks.
- The only authoritative state will be an independently controlled `prp-collab-state` Git ref containing `requirements/<REQ-ID>.json`. Issue titles, checkboxes and labels are projections, not mutexes.
- `main` stays protected. Never automatically merge, deploy, run SSH, use production DB/Keycloak or install MCP as part of the coordination workflow.
- Current phase implements the pure contract and templates. **No live task coordinator is activated by this PR.** Claims become authoritative only when the separately reviewed coordinator is deployed, initialized and tested.
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

The pure `core.mjs` module implements dependency validation, path reservation, state transitions, idempotent command receipts and fail-closed approval requirements. This is **not yet an atomic cross-process Git coordinator**. A later review-only change will add a trusted workflow-dispatch wrapper with Git fast-forward compare-and-swap retries, verify GitHub reviewers/CI and reconcile Issue projections. No user-provided Issue content may execute as shell commands.

## Start and acceptance checks

Run locally from the repo root:

```bash
node --test app/scripts/dev-collab/core.test.mjs
```

Before a real multi-session acceptance, verify two simultaneous claims for the same task lead to one winner, independent tasks can both progress, duplicate request IDs are idempotent, stale claims fail, issue projection failures can be reconciled, unauthorized users fail closed, and no production deployment occurs.

## Planned work items

- T-001 #133 contract/tests (this PR)
- T-002 #134 Issue/PR templates (this PR)
- T-003 #135 trusted workflow coordinator and atomic Git state writes (not yet live)
- T-004 #136 cross-process/test fixtures and operating guide
- T-005 #137 integration acceptance

A PR being green is evidence of tests passing; it is not evidence that live coordination, OAuth or production release has occurred.
