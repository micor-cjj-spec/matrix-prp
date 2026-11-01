# Evidence-gated task acceptance

A task marked IN_REVIEW is not complete because a GPT conversation reports success. The acceptance verifier binds the task's stored PR number and head SHA to the actual GitHub PR, requires that the PR was merged into the protected requirement integration branch, verifies the merged commit is still contained in that branch, and requires all exact GitHub Actions checks to be green on the submitted head SHA. Missing pages, a moved PR, foreign repo, missing required job, unprotected integration branch, stale failure or absent evidence fail closed.

This verifier is a read-only policy function: it does not set DONE, dispatch workflows or grant human acceptance itself. A separately trusted acceptance workflow must fetch these objects using GitHub APIs and revalidate immediately before performing the Git compare-and-swap update.

When every task is DONE, the requirement close gate additionally requires explicit repository-owner acceptance and a separately verified integration-review decision. A boolean flag supplied by an LLM, an ordinary Issue comment or an untrusted pull request is not acceptable evidence; only a trusted workflow context may provide it.

## Separation from routine ChatGPT operations

The owner-authenticated Issue ingress supports task registration, claim, progress, checkpoint, pause/resume, handoff, takeover, submit and fixed V0→V1 migration. It intentionally does not expose accept or close. Those are high-impact review decisions and remain on the separate trusted acceptance path. This separation does not add GitHub GUI approvals to routine task operations.

## Current live boundary

- main is protected by active Ruleset #24968649, with no bypass actors.
- prp-collab-state is protected by active Ruleset #26294671, with the dedicated Integration App as its only configured bypass actor.
- main retains app/deploy/publication-hold.json; production publication remains frozen.
- Formal state remains V0. No task has been accepted as DONE and no protected integration-branch acceptance has been demonstrated.

All tests use fabricated GitHub API objects for the policy functions. They do not demonstrate a live PR merge, a protected integration branch or real task acceptance. The Issue ingress also remains a Draft PR candidate until the one-time bootstrap merge, Environment setup and real Issue/App write test are complete.
