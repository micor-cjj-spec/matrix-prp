import { CollabError } from './core.mjs'

// GitHub-hosted event identity, not a flag supplied in recovery_payload or user text.
// This is only one layer: the workflow also enforces an owner-only job and a
// required-reviewer environment before minting the dedicated App token.
export function trustedRecoveryContext(env) {
  const repo=env.GITHUB_REPOSITORY
  const expected=repo+'/.github/workflows/prp-collab-coordinator.yml@refs/heads/main'
  if(env.GITHUB_ACTIONS!=='true' || env.GITHUB_EVENT_NAME!=='workflow_dispatch' ||
    repo!=='micor-cjj-spec/matrix-prp' ||
    env.GITHUB_REF!=='refs/heads/main' ||
    env.GITHUB_WORKFLOW_REF!==expected ||
    !env.GITHUB_ACTOR || env.GITHUB_ACTOR!==env.GITHUB_REPOSITORY_OWNER ||
    !/^[a-f0-9]{40}$/.test(env.GITHUB_SHA||'')) {
    throw new CollabError('UNTRUSTED_RECOVERY_CONTEXT')
  }
  return { recoveryAuthorized:true }
}
