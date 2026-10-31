import { CollabError } from './core.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'

const REPO = 'micor-cjj-spec/matrix-prp'
const WORKFLOW_FOR_CHECK = Object.freeze({
  'backend-tests': '.github/workflows/ci.yml',
  'web-build': '.github/workflows/ci.yml',
  'mobile-build': '.github/workflows/ci.yml',
  'db-migration-integration': '.github/workflows/ci.yml',
  'video-db-integration': '.github/workflows/ci.yml',
  'impact-report': '.github/workflows/feature-impact.yml',
  'dev-collab-contract': '.github/workflows/prp-dev-collab-contract.yml'
})
const WORKFLOW_NAME = Object.freeze({
  '.github/workflows/ci.yml': 'CI',
  '.github/workflows/feature-impact.yml': 'Feature Impact Report',
  '.github/workflows/prp-dev-collab-contract.yml': 'PRP Dev Collaboration Contract'
})
const SHA=/^[a-f0-9]{40}$/
function check(ok,code){if(!ok)throw new CollabError(code)}

export function verifyWorkflowProvenance(checks, {sha,prNumber,baseRef,headRef}, loadRun){
  check(SHA.test(sha) && Number.isSafeInteger(prNumber) && prNumber>0 &&
    typeof baseRef==='string' && baseRef.length>0 &&
    typeof headRef==='string' && headRef.length>0 &&
    typeof loadRun==='function','PROVENANCE_INPUTS')
  check(checks && Number.isInteger(checks.total_count) &&
    Array.isArray(checks.check_runs) && checks.total_count===checks.check_runs.length &&
    checks.total_count<=100,'INCOMPLETE_CHECK_PAGINATION')
  const recent = new Map()
  for(const job of checks.check_runs){
    if(!REQUIRED_CHECKS.includes(job?.name) || job?.app?.slug!=='github-actions') continue
    check(Number.isSafeInteger(job.id)&&job.id>0,'INVALID_CHECK_ID')
    const old=recent.get(job.name)
    if(!old || job.id>old.id)recent.set(job.name,job)
  }
  const seenRun = new Map()
  for(const name of REQUIRED_CHECKS){
    const job=recent.get(name)
    check(job,'CHECK_MISSING_'+name)
    check(job.head_sha===sha && job.status==='completed' && job.conclusion==='success',
      'CHECK_NOT_GREEN_'+name)
    const match=typeof job.details_url==='string' && job.details_url.match(
      /^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
    check(match && Number(match[2])===job.id,'UNTRUSTED_CHECK_DETAILS_'+name)
    const runId=Number(match[1])
    check(Number.isSafeInteger(runId) && runId>0,'UNTRUSTED_WORKFLOW_ID')
    if(!seenRun.has(runId)) seenRun.set(runId,loadRun(runId))
    const run=seenRun.get(runId)
    const expected=WORKFLOW_FOR_CHECK[name]
    check(run?.path===expected && run?.name===WORKFLOW_NAME[expected],
      'WRONG_CHECK_WORKFLOW_'+name)
    check(run?.event==='pull_request' && run?.status==='completed' &&
      run?.conclusion==='success' && run?.head_sha===sha &&
      run?.head_branch===headRef &&
      run?.repository?.full_name===REPO && run?.head_repository?.full_name===REPO,
      'WRONG_WORKFLOW_ORIGIN_'+name)
    check(Array.isArray(run?.pull_requests) && run.pull_requests.some(pr=>
      pr.number===prNumber && pr.head?.sha===sha && pr.base?.ref===baseRef),
      'WORKFLOW_PR_MISMATCH_'+name)
  }
  return Object.freeze({verified:true,workflow_runs:[...seenRun.keys()].sort((a,b)=>a-b)})
}
