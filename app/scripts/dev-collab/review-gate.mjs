import { CollabError, validateSnapshot } from './core.mjs'

const SHA=/^[a-f0-9]{40}$/
export const REQUIRED_CHECKS=Object.freeze([
  'backend-tests', 'web-build', 'mobile-build', 'db-migration-integration',
  'video-db-integration', 'impact-report', 'dev-collab-contract'
])

function check(ok,code){ if(!ok) throw new CollabError(code) }
function exactIso(s){ return typeof s==='string' && Number.isFinite(Date.parse(s)) }

/**
 * Evidence verification is deliberately read-only. It cannot transition a task or
 * authorize deployment. Future acceptance mutations must re-fetch the evidence
 * under the reviewed workflow immediately before their atomic state update.
 */
export function verifyTaskEvidence(snapshot,taskId,evidence){
  validateSnapshot(snapshot)
  check(snapshot.status==='ACTIVE','REQUIREMENT_NOT_ACTIVE')
  const task=snapshot.tasks.find(t=>t.task_id===taskId)
  check(task,'UNKNOWN_TASK')
  check(task.status==='IN_REVIEW','TASK_NOT_IN_REVIEW')
  check(Number.isInteger(task.pr_number)&&task.pr_number>0&&SHA.test(task.head_sha),'MISSING_TASK_PR_EVIDENCE')
  check(evidence && typeof evidence==='object','MISSING_EVIDENCE')
  const {pr,branch,comparison,checks}=evidence
  const target='integrate/'+snapshot.requirement_id
  check(pr?.number===task.pr_number && pr?.head?.sha===task.head_sha,'WRONG_PR_OR_HEAD')
  check(pr?.base?.ref===target && pr?.base?.repo?.full_name==='micor-cjj-spec/matrix-prp','WRONG_INTEGRATION_BASE')
  check(pr?.head?.repo?.full_name==='micor-cjj-spec/matrix-prp','FOREIGN_HEAD_REPOSITORY')
  check(pr?.merged===true && exactIso(pr?.merged_at) && SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  check(branch?.name===target && branch?.protected===true && SHA.test(branch?.commit?.sha),'UNPROTECTED_INTEGRATION_BRANCH')
  check(comparison?.status==='ahead'||comparison?.status==='identical','MERGE_NOT_ON_BASE')
  check(Number.isInteger(comparison.behind_by)&&comparison.behind_by===0,'MERGE_NOT_ON_BASE')
  check(comparison.base_commit?.sha===pr.merge_commit_sha &&
    comparison.merge_base_commit?.sha===pr.merge_commit_sha &&
    comparison.commits!==undefined,'COMPARE_PROVENANCE_MISMATCH')
  check(checks && Number.isInteger(checks.total_count) && checks.total_count===checks.check_runs?.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  const evidenceMap=new Map()
  for(const run of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(run?.name) || run?.app?.slug!=='github-actions')continue
    const previous=evidenceMap.get(run.name)
    if(!previous||new Date(run.started_at).getTime()>new Date(previous.started_at).getTime()) {
      evidenceMap.set(run.name,run)
    }
  }
  for(const name of REQUIRED_CHECKS){
    const run=evidenceMap.get(name)
    check(run,'CHECK_MISSING_'+name)
    check(run.head_sha===task.head_sha&&run.status==='completed'&&run.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
  }
  return Object.freeze({
    task_id:taskId, pr_number:task.pr_number, head_sha:task.head_sha,
    integration_sha:branch.commit.sha, merge_commit_sha:pr.merge_commit_sha,
    checks:REQUIRED_CHECKS.length, verified:true
  })
}

export function verifyRequirementClose(snapshot, acceptance){
  validateSnapshot(snapshot)
  check(snapshot.status==='ACTIVE','REQUIREMENT_NOT_ACTIVE')
  check(snapshot.tasks.every(t=>t.status==='DONE'),'INCOMPLETE_REQUIREMENT')
  check(acceptance?.actorIsRepositoryOwner===true,'OWNER_APPROVAL_REQUIRED')
  check(acceptance?.explicitAcceptance===true,'EXPLICIT_ACCEPTANCE_REQUIRED')
  check(acceptance?.integrationReviewVerified===true,'INTEGRATION_REVIEW_REQUIRED')
  return Object.freeze({requirement_id:snapshot.requirement_id,ready_to_close:true,version:snapshot.version})
}
