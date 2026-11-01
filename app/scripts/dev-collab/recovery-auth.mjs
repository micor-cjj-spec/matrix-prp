import { CollabError } from './core.mjs'
import { execFileSync } from 'node:child_process'

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

/** The Git ref must exist at precisely the recorded SHA in the checked-out repo.
 * This only verifies immutable remote Git evidence, not the summary's correctness.
 */
export function verifyRecoveryGitBranch(checkpoint, env, git=execFileSync) {
  trustedRecoveryContext(env)
  const branch=checkpoint?.branch, sha=checkpoint?.head_sha
  if(typeof branch!=='string' ||
    !/^[a-zA-Z0-9][a-zA-Z0-9_.\/-]{0,119}$/.test(branch) ||
    branch.includes('..') || branch.includes('//') ||
    branch.endsWith('/') || branch.endsWith('.') || branch.endsWith('.lock') ||
    branch==='main' || branch==='prp-collab-state' ||
    typeof sha!=='string' || !/^[a-f0-9]{40}$/.test(sha)) {
    throw new CollabError('INVALID_RECOVERY_GIT_REFERENCE')
  }
  const ref='refs/heads/'+branch
  let output
  try{
    output=git('git',['ls-remote','--exit-code','--refs','origin',ref],{
      encoding:'utf8',timeout:12000,maxBuffer:8192
    })
  }catch{
    throw new CollabError('RECOVERY_REMOTE_REF_UNAVAILABLE')
  }
  if(typeof output!=='string' ||
    output.trim()!==sha+'\t'+ref)throw new CollabError('RECOVERY_GIT_HEAD_MISMATCH')
  return {gitEvidenceVerified:true}
}
