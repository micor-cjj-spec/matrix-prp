# PRP CI/CD V2 — GitHub-only release readiness request

**Current status:** proposal and isolated contract tests. This does not remove any publication hold, grant production permission, or verify the running server.

## Purpose

Avoid manual GitHub navigation for the **first, read-only** release precheck. A future conversation can request a check through a single owner-authored comment on Issue #323; the default-branch Action will publish a sanitized, read-only report. It does not need an SSH credential or an operational tool on the server.

Exact comment syntax, after this workflow has been separately reviewed and merged to `main`:

```text
PRP-RELEASE-CHECK sha=<exact 40-character lowercase main commit SHA>
```

Until this proposal is merged to `main`, the new issue-comment handler does **not** exist on the live default branch and cannot process a request.

## Technical controls

- Only `issue_comment.created` on Issue #323, authored by the repository owner, with an exact full-body command. All other events are rejected or skipped.
- Workflow executes from default branch, checks out exact `github.sha`, then queries trusted GitHub API for current `main` and the **latest** exact-SHA successful main-push CI run. A CI from a PR/fork, stale commit, or later failed run is not accepted.
- Checks six mandatory jobs: backend, Web, mobile, DB migration, video database integration and deployment gate tests. Missing or incomplete job enumeration fails closed.
- Validates the checked-in `publication-hold.json` syntax and records the hold state. While it exists, the result is `HELD`, regardless of successful CI.
- Script has no network destination besides the GitHub API, uses only automatic read-only GitHub token permissions and does **not** request a `production` environment or deploy SSH identity.
- Always emits `production_authorized=false` and `production_live_verified=false`. Staging, UAT, production backup/rollback, owner release approval and live controller/readback are explicitly **NOT CHECKED**.
- Negative tests exercise identity/command verification, SHA mismatches, stale CI, missing/duplicate failed jobs, and hold validation.

## Next step after non-production review

Create a separately trusted report aggregating independent staging, backup, migration, owner approval, release artifact and production controller evidence. The default-branch release policy should eventually use it as a *precondition*, never as a substitute for the existing `Deploy PRP` production environment gates.

This proposal must **not** be taken as authority to merge `dev`, change branch protection, remove the global hold, or deploy PRP.

## Consolidation safeguards

The collector verifies the actual Git checkout SHA, enumerates the selected immutable CI attempt (including extra jobs), rejects incomplete enumeration, and checks that main and the run inventory did not move during the observation. Exact owner command parsing also rejects a final newline. These checks reduce inconsistent snapshots but are not a production release authorization or a transactional lock.
