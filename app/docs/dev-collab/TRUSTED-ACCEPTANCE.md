# Trusted manual acceptance review path

The manual-only `PRP Collaboration Coordinator` may accept a task only after a repository-owner `workflow_dispatch` on protected `main`, with exact `pr_number`, `head_sha`, `task_id` and a unique request UUID. It fetches the actual GitHub PR, the protected `integrate/<REQ-ID>` branch, a GitHub compare proof and the complete check runs for the stored PR head SHA. Every required check must be a successful GitHub Actions check. Missing, moved, unmerged, failed or unsigned evidence is rejected. The reviewer context cannot be supplied through workflow inputs and is recomputed on each Git CAS retry.

For `close`, the owner explicitly supplies the final merged integration PR number and final submitted head SHA targeting protected `main`. All tasks must already be DONE. The main branch must contain the merge commit and have all required exact-head checks green. Merely finishing tasks, passing CI or typing `done` cannot close a requirement.

**Critical:** acceptance into an integration branch needs real PR CI for that branch. Existing PRP workflows are `main`-targeted, so a separate reviewed integration-CI configuration change is needed before any live task can pass this gate. Branch protection must permit only the trusted runner to update `prp-collab-state`; protection that blocks all writes is safe but unusable. No rights or protection configuration is changed by this PR.

This owner-triggered workflow is a review mechanism, **not** permission to bypass production publication gates. Merging the final integration PR into `main` may trigger the existing production release workflow, and requires separate authorized release governance.

## GitHub Actions workflow provenance (additional required proof)

Green checks are not accepted by their display name alone. The verifier reads each check's GitHub Actions `details_url`, requires that its run/job identifiers match the actual check, and independently fetches the owning workflow run. The run must be a completed successful `pull_request` execution of the exact approved workflow file (CI, Feature Impact Report, or PRP Dev Collaboration Contract), in this repository, on the stored task head SHA and associated with the exact PR number and base branch. A manually dispatched fake workflow or another check job with the same name fails closed. Real run metadata has been checked against existing PR #138, but end-to-end acceptance on a protected integration branch is still pending.
