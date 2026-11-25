import { execFileSync } from 'node:child_process'
import { CollabError } from './core.mjs'
import { verifyTaskEvidence, verifyIntegrationRelease, verifyRequirementClose, verifyIntegrationPolicy } from './review-gate.mjs'
import { verifyWorkflowProvenance } from './review-provenance.mjs'

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
  const manual=env.GITHUB_EVENT_NAME==='workflow_dispatch' && env.GITHUB_WORKFLOW_REF===REPO+'/.github/workflows/prp-collab-coordinator.yml@refs/heads/main'
  const issue=env.GITHUB_EVENT_NAME==='issues' && env.GITHUB_EVENT_ACTION==='opened' && env.GITHUB_WORKFLOW_REF===REPO+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'
  check(SHA.test(env.GITHUB_SHA||'') && (manual || (issue && command.type==='accept')),'UNTRUSTED_REVIEW_ENTRYPOINT')
  const root='repos/'+REPO
  const requirePolicy=()=>verifyIntegrationPolicy(snapshot.requirement_id,api(root+'/rulesets/28050327'))
  const requireMain=main=>check(main?.name==='main' && main.protected===true && main.commit?.sha===env.GITHUB_SHA,'REVIEW_MAIN_REVISION_MISMATCH')
  const loadJobs=id=>api(root+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest')
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
    const files=api(`repos/${REPO}/pulls/${task.pr_number}/files?per_page=100`)
    verifyTaskEvidence(snapshot,command.task_id,{pr,branch,comparison,checks,files})
    requireMain(api(root+'/branches/main'))
    requirePolicy()
    verifyWorkflowProvenance(checks,{sha:task.head_sha,prNumber:task.pr_number,
      baseRef:integrationRef,headRef:pr.head.ref,mergedAt:pr.merged_at},id=>api(`repos/${REPO}/actions/runs/${id}`),loadJobs)
    return {reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true}
  }
  check(Number.isInteger(command.pr_number)&&SHA.test(command.head_sha),'MISSING_INTEGRATION_PR')
  const pr=api(`repos/${REPO}/pulls/${command.pr_number}`)
  const branch=api(`repos/${REPO}/branches/main`)
  check(SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  const comparison=api(`repos/${REPO}/compare/${pr.merge_commit_sha}...${branch.commit.sha}`)
  // Require a distinct protected integration history to be included in the
  // exact dev head subsequently merged into main. No cherry-pick approximation.
  const integrationBranch=api(`repos/${REPO}/branches/${encodeURIComponent(integrationRef)}`)
  const integrationComparison=api(`repos/${REPO}/compare/${integrationBranch.commit.sha}...${command.head_sha}`)
  // Prove the tested dev PR head itself survived into the protected main
  // history, not merely that a squash PR reported "merged".
  const mainAncestryComparison=api(`repos/${REPO}/compare/${command.head_sha}...${branch.commit.sha}`)
  const checks=api(`repos/${REPO}/commits/${command.head_sha}/check-runs?per_page=100`)
  verifyIntegrationRelease(snapshot,command,
    {pr,branch,comparison,checks,integrationBranch,integrationComparison,
      mainAncestryComparison})
  requireMain(branch)
  requirePolicy()
  verifyWorkflowProvenance(checks,{sha:command.head_sha,prNumber:command.pr_number,
    baseRef:'main',headRef:pr.head.ref,mergedAt:pr.merged_at},id=>api(`repos/${REPO}/actions/runs/${id}`),loadJobs)
  verifyRequirementClose(snapshot,{
    actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true
  })
  return {reviewerAuthorized:true,acceptanceApproved:true,integrationReviewVerified:true}
}
