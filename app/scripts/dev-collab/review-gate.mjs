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
  const {pr,branch,comparison,checks,files}=evidence
  const target='integrate/'+snapshot.requirement_id
  check(pr?.number===task.pr_number && pr?.head?.sha===task.head_sha,'WRONG_PR_OR_HEAD')
  verifyTaskChangedFiles(task,pr,files)
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
  verifyCheckSet(checks,task.head_sha)
  return Object.freeze({
    task_id:taskId, pr_number:task.pr_number, head_sha:task.head_sha,
    integration_sha:branch.commit.sha, merge_commit_sha:pr.merge_commit_sha,
    checks:REQUIRED_CHECKS.length, verified:true
  })
}

const CRITICAL_WORKFLOWS = new Set([
  '.github/workflows/ci.yml',
  '.github/workflows/feature-impact.yml',
  '.github/workflows/prp-dev-collab-contract.yml'
])
const filePath = s => typeof s==='string' && s.length>0 &&
  !s.startsWith('/') && !s.includes('\\') && !s.split('/').includes('..')
function withinScope(file,scopes){
  return scopes.some(s=>s===file || (s.endsWith('/') && file.startsWith(s)))
}
export function verifyTaskChangedFiles(task,pr,files){
  check(Number.isInteger(pr?.changed_files) && pr.changed_files>0 &&
    pr.changed_files<=100 && Array.isArray(files) && files.length===pr.changed_files,
    'INCOMPLETE_PR_FILE_LIST')
  check(Array.isArray(task?.allowed_paths) && task.allowed_paths.length>0,'TASK_HAS_NO_WRITE_SCOPE')
  const seen=new Set()
  for(const file of files){
    const name=file?.filename
    check(filePath(name) && !seen.has(name),'INVALID_OR_DUPLICATE_PR_FILE')
    seen.add(name)
    check(!CRITICAL_WORKFLOWS.has(name),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
    check(withinScope(name,task.allowed_paths),'TASK_FILE_OUTSIDE_SCOPE')
    if(file.status==='renamed'){
      check(filePath(file.previous_filename) && withinScope(file.previous_filename,task.allowed_paths),
        'RENAME_SOURCE_OUTSIDE_SCOPE')
    }
  }
  return Object.freeze({verified:true,files:seen.size})
}

function verifyCheckSet(checks,sha){
  check(checks && Number.isInteger(checks.total_count) &&
    Array.isArray(checks.check_runs) &&
    checks.total_count === checks.check_runs.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  const evidenceMap=new Map()
  for(const run of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(run?.name) || run?.app?.slug!=='github-actions')continue
    const previous=evidenceMap.get(run.name)
    check(Number.isSafeInteger(run.id) && run.id>0,'INVALID_CHECK_ID')
    if(!previous||run.id>previous.id) {
      evidenceMap.set(run.name,run)
    }
  }
  for(const name of REQUIRED_CHECKS){
    const run=evidenceMap.get(name)
    check(run,'CHECK_MISSING_'+name)
    check(run.head_sha===sha&&run.status==='completed'&&run.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
  }
  return true
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


export function verifyIntegrationRelease(snapshot,command,proof){
  validateSnapshot(snapshot)
  check(snapshot.tasks.every(t=>t.status==='DONE'),'INCOMPLETE_REQUIREMENT')
  check(Number.isInteger(command.pr_number) && SHA.test(command.head_sha),'MISSING_INTEGRATION_PR')
  const {pr,branch,comparison,checks}=proof ?? {}
  check(pr?.number===command.pr_number&&pr?.head?.sha===command.head_sha,'WRONG_PR_OR_HEAD')
  check(pr?.head?.ref==='integrate/'+snapshot.requirement_id &&
        pr?.head?.repo?.full_name==='micor-cjj-spec/matrix-prp' &&
        pr?.base?.ref==='main'&&pr?.base?.repo?.full_name==='micor-cjj-spec/matrix-prp',
        'WRONG_MAIN_RELEASE_TARGET')
  check(pr?.merged===true&&exactIso(pr?.merged_at)&&SHA.test(pr?.merge_commit_sha),'PR_NOT_MERGED')
  check(branch?.name==='main'&&branch?.protected===true&&SHA.test(branch?.commit?.sha),'MAIN_NOT_PROTECTED')
  check((comparison?.status==='ahead'||comparison?.status==='identical')&&
    comparison.behind_by===0&&comparison.base_commit?.sha===pr.merge_commit_sha&&
    comparison.merge_base_commit?.sha===pr.merge_commit_sha,'MERGE_NOT_ON_BASE')
  verifyCheckSet(checks,command.head_sha)
  return Object.freeze({integration_pr:command.pr_number,verified:true,main_sha:branch.commit.sha})
}
