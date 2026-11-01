#!/usr/bin/env bash
# Owner-only, one-shot and non-force. This script may only run from reviewed main.
set -Eeuo pipefail
fail(){ echo "PRP_COLLAB_MIGRATION_BLOCKED=$1" >&2; exit 2; }
[[ "$GITHUB_ACTIONS" == true && "$GITHUB_EVENT_NAME" == workflow_dispatch ]] || fail EVENT
[[ "$GITHUB_REPOSITORY" == 'micor-cjj-spec/matrix-prp' ]] || fail REPOSITORY
[[ "$GITHUB_REF" == 'refs/heads/main' ]] || fail SOURCE_REF
[[ "$GITHUB_WORKFLOW_REF" == 'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-migration.yml@refs/heads/main' ]] || fail WORKFLOW_SOURCE
[[ -n "$GITHUB_ACTOR" && "$GITHUB_ACTOR" == "$GITHUB_REPOSITORY_OWNER" ]] || fail OWNER
[[ "$COLLAB_MIGRATION_MODE" == verify || "$COLLAB_MIGRATION_MODE" == apply ]] || fail MODE
[[ "$COLLAB_EXPECTED_STATE_SHA" =~ ^[a-f0-9]{40}$ ]] || fail STATE_SHA
[[ "$COLLAB_EXPECTED_PROPOSAL_SHA" =~ ^[a-f0-9]{40}$ ]] || fail PROPOSAL_SHA
# Immutable, independently reviewed SHA pins; inputs cannot select a different proposal.
[[ "${COLLAB_APPROVED_STATE_SHA:-}" =~ ^[a-f0-9]{40}$ ]] || fail APPROVED_STATE_PIN_CONFIG
[[ "${COLLAB_APPROVED_PROPOSAL_SHA:-}" =~ ^[a-f0-9]{40}$ ]] || fail APPROVED_PROPOSAL_PIN_CONFIG
[[ "$COLLAB_EXPECTED_STATE_SHA" == "$COLLAB_APPROVED_STATE_SHA" ]] || fail UNAPPROVED_STATE_SHA
[[ "$COLLAB_EXPECTED_PROPOSAL_SHA" == "$COLLAB_APPROVED_PROPOSAL_SHA" ]] || fail UNAPPROVED_PROPOSAL_SHA
[[ "$COLLAB_RULESET_ID" == '26294671' ]] || fail RULESET_ID
[[ "$COLLAB_APP_ID" == '5561446' ]] || fail APP_ID
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]] || fail SOURCE_SHA
[[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]] || fail SOURCE_REVISION
[[ -f app/deploy/publication-hold.json ]] || fail PUBLICATION_HOLD_MISSING
node -e 'const x=JSON.parse(require("fs").readFileSync("app/deploy/publication-hold.json","utf8")); if(x.schema_version!==1 || typeof x.reason!=="string" || x.reason.trim().length===0)process.exit(2)' || fail PUBLICATION_HOLD_INVALID
main_head="$(git ls-remote --exit-code --refs origin refs/heads/main | cut -f1)"
[[ "$main_head" == "$GITHUB_SHA" ]] || fail MAIN_HEAD_MOVED
[[ -n "$COLLAB_APP_TOKEN" ]] || fail DEDICATED_APP_TOKEN
if [[ "$COLLAB_MIGRATION_MODE" == apply ]]; then
  [[ "$COLLAB_APPROVAL_PHRASE" == 'APPLY-REQ-20261031-001-V1' ]] || fail EXPLICIT_APPROVAL
fi

root="$(pwd -P)"
dir="$RUNNER_TEMP/prp-collab-migration"
mkdir -p "$dir"
file='requirements/REQ-20261031-001.json'
git fetch --no-tags origin refs/heads/prp-collab-state
state_sha="$(git rev-parse FETCH_HEAD)"
[[ "$state_sha" == "$COLLAB_EXPECTED_STATE_SHA" ]] || fail STATE_MOVED_OR_MIGRATED
git fetch --no-tags origin refs/heads/proposal/prp-collab-state-scope-20261101
proposal_sha="$(git rev-parse FETCH_HEAD)"
[[ "$proposal_sha" == "$COLLAB_EXPECTED_PROPOSAL_SHA" ]] || fail PROPOSAL_MOVED
git merge-base --is-ancestor "$state_sha" "$proposal_sha" || fail PROPOSAL_BASE
[[ "$(git diff --name-only "$state_sha" "$proposal_sha")" == "$file" ]] || fail PROPOSAL_DIFF_SCOPE
git show "$state_sha:$file" > "$dir/before.json"
git show "$proposal_sha:$file" > "$dir/after.json"

# Paths and PR identifiers are constants, never interpreted from Issue comments.
gh api "repos/$GITHUB_REPOSITORY/pulls/144" > "$dir/pr.json"
gh api "repos/$GITHUB_REPOSITORY/pulls/144/files?per_page=100" > "$dir/pr-files.json"
gh api "repos/$GITHUB_REPOSITORY/pulls/144/reviews?per_page=100" > "$dir/pr-reviews.json"
GH_TOKEN="$COLLAB_APP_TOKEN" gh api "repos/$GITHUB_REPOSITORY/rulesets/$COLLAB_RULESET_ID" > "$dir/ruleset.json"
app_repos='-'
if [[ "$COLLAB_MIGRATION_MODE" == apply ]]; then
  GH_TOKEN="$COLLAB_APP_TOKEN" gh api installation/repositories > "$dir/app-repos.json"
  app_repos="$dir/app-repos.json"
fi
node "$root/app/scripts/dev-collab/migration-guard.mjs" \
  "$dir/before.json" "$dir/after.json" "$dir/pr.json" \
  "$dir/pr-files.json" "$dir/ruleset.json" "$dir/pr-reviews.json" "$app_repos"

if [[ "$COLLAB_MIGRATION_MODE" == verify ]]; then
  echo 'PRP_COLLAB_MIGRATION=VERIFIED_READ_ONLY'
  exit 0
fi

# Check both refs again after approval and verification; never retry a stale write.
[[ "$(git ls-remote --exit-code --refs origin refs/heads/main | cut -f1)" == "$GITHUB_SHA" ]] || fail MAIN_HEAD_RACE
[[ "$(git ls-remote --refs origin refs/heads/prp-collab-state | cut -f1)" == "$state_sha" ]] || fail STATE_RACE
[[ "$(git ls-remote --refs origin refs/heads/proposal/prp-collab-state-scope-20261101 | cut -f1)" == "$proposal_sha" ]] || fail PROPOSAL_RACE
state_worktree="$dir/state-worktree"
git worktree add --detach "$state_worktree" "$state_sha" >/dev/null
cp "$dir/after.json" "$state_worktree/$file"
git -C "$state_worktree" add -- "$file"
[[ "$(git -C "$state_worktree" diff --cached --name-only)" == "$file" ]] || fail STAGED_FILES
git -C "$state_worktree" diff --cached --check || fail PATCH_INVALID
git -C "$state_worktree" config user.name 'prp-collab-writer[bot]'
git -C "$state_worktree" config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git -C "$state_worktree" commit \
  -m "chore(collab): migrate REQ-20261031-001 V0 to V1 (proposal PR #144)" \
  -m "State-base: $state_sha" \
  -m "Proposal-head: $proposal_sha" \
  -m "Requested-by: $GITHUB_ACTOR" \
  -m "Actions-run: $GITHUB_RUN_ID/$GITHUB_RUN_ATTEMPT" >/dev/null
git -C "$state_worktree" push origin HEAD:refs/heads/prp-collab-state || fail NON_FAST_FORWARD_OR_RULESET_DENIED
local_applied_sha="$(git -C "$state_worktree" rev-parse HEAD)"
remote_applied_sha="$(git ls-remote --exit-code --refs origin refs/heads/prp-collab-state | cut -f1)" || fail POST_PUSH_REF_UNAVAILABLE
[[ "$remote_applied_sha" == "$local_applied_sha" ]] || fail POST_PUSH_SHA_MISMATCH
echo "PRP_COLLAB_MIGRATION_APPLIED_SHA=$remote_applied_sha"
