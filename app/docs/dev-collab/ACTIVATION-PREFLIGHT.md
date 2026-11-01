# Administrator activation preflight — read-only

This script is a **NO-GO diagnostic**, not an activation button. It never creates a task claim, app, ruleset, environment, PR, deployment or production database update.

## Current blockers (verified 2026-11-01)

- `prp-collab-state` is currently **unprotected**, at commit `062036f7021e215ffbfdcbf5689d207a0549b68b`.
- Only the `protect-main` ruleset is currently visible. There is no verified exact-branch state ruleset.
- The GitHub connector does not provide the administrator write APIs needed to provision a GitHub App, required-reviewer environment, secret, or state ruleset.
- The authoritative requirement is V0 with no tasks claimed. Existing Draft PR #138 contains bootstrap code, not five separately accepted task PRs; see [Issue #139](https://github.com/micor-cjj-spec/matrix-prp/issues/139).

## Administrator configuration order

1. From the GitHub repository/organization settings, create a **dedicated GitHub App**, repository Contents read/write, installed only for `micor-cjj-spec/matrix-prp`. Store its private key **in GitHub Secrets, never in chat or a file committed to Git**.
2. Add `prp-collab-controller` GitHub Actions environment and require at least one authorized reviewer. Create `PRP_COLLAB_APP_PRIVATE_KEY` environment secret and `PRP_COLLAB_APP_CLIENT_ID` variable. Set numeric `PRP_COLLAB_APP_ID` and `PRP_COLLAB_RULESET_ID` variables.
3. Create an active **branch Ruleset** matching only `refs/heads/prp-collab-state`, with update restriction, deletion restriction, and non-fast-forward prohibition. Grant always-bypass only to the new app. Preserve independent `main` protection, with **no** app bypass on main.
4. In an approved isolated workflow using the app token, verify the installation token grants exactly one repository through GitHub's `GET /installation/repositories` API; check that the environment really requires approval. Do not assume a variable or a secret existing proves the policy is correct.
5. Review Bootstrap [Issue #139](https://github.com/micor-cjj-spec/matrix-prp/issues/139) and prepare an approved migration of original task scopes before a pilot; do not retroactively mark any of the existing tasks DONE.

## Read-only execution

Run on a trusted administrator workstation with GitHub CLI authenticated and an up-to-date checkout that **contains the state commit object**:

```bash
git fetch --no-tags origin refs/heads/prp-collab-state
export PRP_COLLAB_APP_ID='<numeric GitHub App ID>'
export PRP_COLLAB_RULESET_ID='<numeric ruleset ID>'
node app/scripts/dev-collab/activation-preflight.mjs
```

The optional `PRP_COLLAB_APP_TOKEN` environment variable must only be set inside an approved ephemeral Actions job, never placed in commands shared with ChatGPT. Without it the report intentionally shows `DEDICATED_APP_TOKEN_SCOPE_UNVERIFIED`. Without repository-admin API read access, the environment or ruleset check similarly fails closed.

Even an all-green report returns `allow_claim:false`, `allow_merge:false`, and `allow_deploy:false`. **Only an independent review and explicitly approved live pilot** can authorize task mutations.

Source references: GitHub's official `actions/create-github-app-token@v3` documents `client-id` and `private-key`. GitHub Actions supports `queue: max` when `cancel-in-progress` is false. No change to those inputs was needed.
