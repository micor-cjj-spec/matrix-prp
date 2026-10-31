import { execFileSync } from 'node:child_process'
import { CollabError } from './core.mjs'
import { verifyTaskEvidence, verifyIntegrationRelease, verifyRequirementClose } from './review-gate.mjs'

const REPO='micor-cjj-spec/matrix-prp'
const SHA=/^[a-f0-9]{40}$/
function check(ok,code){if(!ok)throw new CollabError(code)}
export function ghApi(route){
  const json=execFileSync('gh',['api',route],{encoding:'utf8',maxBuffer:5*1024*1024})
  return JSON.parse(json)
}

/** The only trust boundary: called exclusively from the owner-initiated reviewed workflow. */
export function trustedReviewContext(snapshot,command,env,api){
  check(env.GITHUB_ACTIONS==='true' && env.GITHUB_REF==='refs/heads/main' &&
    env.GITHUB_REPOSITORY===REPO && env.GITHUB_ACTOR==='micor-cjj-spec' &&
    env.GITHUB_REPOSITORY_OWNER==='micor-cjj-spec' && typeof env.GH_TOKEN==='string' &&
    env.GH_TOKEN.length>0,'UNTRUSTED_REVIEW_CONTEXT')
  check(command.type==='accept'||command.type==='close','INVALID_REVIEW_ACTION')
  const integrationRef='integrate/'+snapshot.requirement_id
  if(command.type==='accept'){
    const task=snapshot.tasks.find(t=>t.task_id===command.task_id)
    check(task && task.status==='IN_REVIEW','TASK_NOT_IN_REVIEW')
    check(command.pr_number===task.pr_number && command.head_sha===task.head_sha,'REVIEW_TASK_MISMATCH')
    const pr=api(`repos/${REPO}/pulls/${task.pr_number}`)
    const branch=api(`repos/${REPO}/branches/${encodeURIComponent(integrationRef)}`)
    check(SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
    const comparison=api(`repos/${REPO}/compare/${pr.merge_commit_sha}...${branch.commit.sha}`)
    const checks=api(`repos/${REPO}/commits/${task.head_sha}/check-runs?per_page=100`)
    verifyTaskEvidence(snapshot,command.task_id,{pr,branch,comparison,checks})
    return {reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true}
  }
  check(Number.isInteger(command.pr_number)&&SHA.test(command.head_sha),'MISSING_INTEGRATION_PR')
  const pr=api(`repos/${REPO}/pulls/${command.pr_number}`)
  const branch=api(`repos/${REPO}/branches/main`)
  check(SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  const comparison=api(`repos/${REPO}/compare/${pr.merge_commit_sha}...${branch.commit.sha}`)
  const checks=api(`repos/${REPO}/commits/${command.head_sha}/check-runs?per_page=100`)
  verifyIntegrationRelease(snapshot,command,{pr,branch,comparison,checks})
  verifyRequirementClose(snapshot,{
    actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true
  })
  return {reviewerAuthorized:true,acceptanceApproved:true,integrationReviewVerified:true}
}
