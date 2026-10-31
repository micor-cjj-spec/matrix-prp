#!/usr/bin/env bash
# Trusted manual coordinator. Runs only from reviewed main after manual workflow_dispatch.
set -Eeuo pipefail

[[ "${GITHUB_REF:-}" == 'refs/heads/main' ]] || { echo 'REF_NOT_MAIN'; exit 2; }
[[ -n "${GITHUB_ACTOR:-}" && "${GITHUB_ACTOR}" == "${GITHUB_REPOSITORY_OWNER:-}" ]] || {
  echo 'OWNER_ONLY'; exit 2;
}
[[ "${COLLAB_REQ_ID:-}" =~ ^REQ-[0-9]{8}-[0-9]{3}$ ]] || { echo 'INVALID_REQ_ID'; exit 2; }
if [[ "${COLLAB_ACTION:-}" == 'close' ]]; then
  [[ -z "${COLLAB_TASK_ID:-}" ]] || { echo 'CLOSE_HAS_TASK_ID'; exit 2; }
else
  [[ "${COLLAB_TASK_ID:-}" =~ ^T-[0-9]{3}$ ]] || { echo 'INVALID_TASK_ID'; exit 2; }
fi
[[ "${COLLAB_REQUEST_ID:-}" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || {
  echo 'INVALID_REQUEST_ID'; exit 2;
}
[[ "${COLLAB_ACTION:-}" =~ ^(claim|start|progress|pause|block|resume|release|submit|rework|accept|close)$ ]] || {
  echo 'INVALID_ACTION'; exit 2;
}

if [[ -n "${GITHUB_SHA:-}" && "$(git rev-parse HEAD)" != "$GITHUB_SHA" ]]; then
  echo 'SOURCE_REVISION_MISMATCH'; exit 2
fi

root="$(pwd -P)"
state="${RUNNER_TEMP:?}/prp-collab-state-worktree"
receipt="${RUNNER_TEMP:?}/prp-collab-receipt.json"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

# Re-read remote state for every attempt; no force push, no production or PRP runtime access.
for attempt in 1 2 3; do
  git fetch --no-tags origin refs/heads/prp-collab-state
  fetched="$(git rev-parse FETCH_HEAD)"
  if [[ -e "$state/.git" ]]; then
    git -C "$state" reset --hard "$fetched" >/dev/null
  else
    git worktree add --detach "$state" "$fetched" >/dev/null
  fi
  file="requirements/${COLLAB_REQ_ID}.json"
  [[ -f "$state/$file" ]] || { echo 'REQUIREMENT_NOT_REGISTERED'; exit 3; }
  node "$root/app/scripts/dev-collab/coordinator-cli.mjs" "$state/$file" "$receipt"
  git -C "$state" add -- "$file"
  if git -C "$state" diff --cached --quiet; then
    echo 'PRP_COLLAB_IDEMPOTENT_REPLAY=YES'
    cat "$receipt"
    exit 0
  fi
  git -C "$state" commit -m "chore(collab): ${COLLAB_ACTION} ${COLLAB_REQ_ID}/${COLLAB_TASK_ID}" >/dev/null
  if git -C "$state" push origin HEAD:refs/heads/prp-collab-state; then
    echo 'PRP_COLLAB_STATE_COMMITTED=YES'
    cat "$receipt"
    exit 0
  fi
  echo "STATE_RACE_OR_PUSH_REJECTION attempt=$attempt" >&2
done

echo 'STATE_CONTENTION_OR_PUSH_DENIED' >&2
exit 4
