# PRP Collaboration MVP: review and operator boundaries

Parent: [#132](https://github.com/micor-cjj-spec/matrix-prp/issues/132).
Draft implementation: task state-machine, Issue/PR templates and a **manual-only** GitHub Actions coordinator.

## Activation is not automatic

The coordinator workflow is only runnable after a separately reviewed merge to the default branch. This PR does not merge itself and does not trigger manual workflow_dispatch. `main` CI can trigger an independent existing production deployment pipeline, so no merge without separately verifying production publication gates and authorization.

The dedicated `prp-collab-state` ref stores JSON task state at `requirements/<REQ-ID>.json`. This is not the PRP production database. Before operational use, enforce branch rules prohibiting unauthorized direct writes/force pushes; otherwise trusted task transitions could be bypassed by someone with Git write access. The manual coordinator now checks the GitHub branch's `protected` flag and refuses writes when it is false. This is necessary but **not sufficient**: an independent reviewer must also inspect the actual rule set and bypass actors, ensure only the trusted coordinator actor can push, and demonstrate a successful non-force write using an approved isolated test. An unprotected branch currently makes live claims intentionally fail closed. The branch may be seeded by a maintainer with registered Issue IDs; never expose secrets or task prompts containing credentials in public JSON or Actions logs.

## How an operator can run a task command after review

1. Open Actions → PRP Collaboration Coordinator → Run workflow, selecting `main`.
2. Set `action=claim`, Requirement `REQ-20261031-001`, Task `T-002`, a new UUID `request_id`, and a short advisory `worker_id`.
3. The workflow's GitHub actor must be the repository owner. Read the final run log: only `PRP_COLLAB_STATE_COMMITTED=YES` and the returned `claim_id` certify success.
4. Repeat with `start` and the exact `claim_id`, `worker_id`, a fresh `request_id`.
5. New GPT conversations fetch `requirements/<REQ-ID>.json` from `prp-collab-state` and read the latest version.

The controller checks the pinned event source SHA to prevent unreviewed source drift, then uses reviewed main source, validates input, edits a disposable Git worktree and does a **non-force push**. Push failure causes a fresh fetch and revalidation; three failures return a retryable error. No GitHub Action ever executes text from Issue comments as shell. GitHub's concurrency queue is a supplemental guard; the non-fast-forward push is the last safety boundary.

## Important limitations to finish before marking MVP fully operational

- Task `accept` and requirement `close` require trusted reviewer/CI/integration evidence and are deliberately **not exposed** in the manual workflow. T-005 must implement that separate verified approval path.
- Issue labels and checkbox views are not automatically mirrored yet. The state JSON is authoritative; the Issue view may lag. Reconciliation needs a separate trusted idempotent workflow.
- A human must inspect each Draft PR, allowed file changes and appropriate CI before integration. GitHub `main` and production release protections remain unchanged.
- This GitHub Actions manual dispatch is not callable from every ChatGPT client automatically; connected GitHub API permissions and workflow dispatch tool support determine automation. Until then a user/operator dispatches the command.
- GitHub user identity authenticates commands. `worker_id` and `claim_id` are coordination handles, **not security secrets** or proof of separate ChatGPT conversations.

## Verification

```bash
node --test app/scripts/dev-collab/*.test.mjs
bash -n app/scripts/dev-collab/state-transaction.sh
```

Required manual acceptance: two near-simultaneous workflow dispatches claiming one READY task produce only one committed claim; two non-overlapping READY tasks can be claimed; wrong actor, stale claim, replayed request, blocked dependency, scope overlap and unauthorized workflow ref fail closed. No automatic merge or production effects are authorized.

## Read-only task board (available after reviewed merge)

Any GPT with access to the GitHub repository can directly read `requirements/REQ-20261031-001.json` from the dedicated state branch. The proposed manual `PRP Collaboration Board` Actions workflow fetches a pinned state commit and renders a sanitized, no-write task table in GitHub Actions Summary. Its output deliberately omits `claim_id`, request ledger fingerprints, private notes and other command internals. This is a non-authoritative **display** of committed state, not a claim or update action.

For offline read-only preview: `node app/scripts/dev-collab/board.mjs /path/to/REQ-20261031-001.json`.
