# Evidence-gated task acceptance (review-only phase)

A task marked `IN_REVIEW` is not complete because a GPT conversation reports success. The acceptance verifier binds the task's stored PR number and head SHA to the actual GitHub PR, requires that the PR was merged **into the protected requirement integration branch**, verifies the merged commit is still contained in that branch, and requires all seven exact GitHub Actions checks to be green on the submitted head SHA. Missing pages, a moved PR, foreign repo, missing required job, unprotected integration branch, stale failure or absent evidence fail closed.

This initial verifier module is deliberately a **read-only policy function**: it does not set `DONE`, does not dispatch workflows and does not grant human acceptance itself. A separately authorized future acceptance workflow must fetch these objects using trusted GitHub APIs and revalidate immediately before performing the Git compare-and-swap update.

When every task is DONE, the requirement close gate additionally requires explicit repository-owner approval and a separately verified integration-review decision. A boolean flag supplied by an LLM, an Issue comment or untrusted pull request is not acceptable evidence; only a trusted workflow context may provide it.

All tests use fabricated GitHub API objects. They do **not** demonstrate a live PR merge, a protected integration branch, or real task acceptance. The actual state branch is still unprotected and the coordinator must remain inactive.
