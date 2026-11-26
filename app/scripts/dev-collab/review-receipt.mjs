// Review-only receipt contract. These pure functions neither read nor write Git.
// A caller MUST obtain evidence from GitHub and load the persisted receipt from
// a reviewed protected-state writer. A digest is not authorization or a signature.
import {createHash} from 'node:crypto'
import {CollabError,validateSnapshot} from './core.mjs'
import {REQUIRED_CHECKS,verifyTaskChangedFiles,verifyTaskEvidence} from './review-gate.mjs'
import {verifyWorkflowProvenance} from './review-provenance.mjs'

const REPO='micor-cjj-spec/matrix-prp',REPO_ID=1261866723,APP_ID=15368
const SHA=/^[a-f0-9]{40}$/
const CI='.github/workflows/ci.yml',IMPACT='.github/workflows/feature-impact.yml',CONTRACT='.github/workflows/prp-dev-collab-contract.yml'
const PATHS=[CI,IMPACT,CONTRACT]
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const time=v=>typeof v==='string'?Date.parse(v):NaN
const canon=v=>Array.isArray(v)?'['+v.map(canon).join(',')+']':
 v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canon(v[k])).join(',')+'}':JSON.stringify(v)
const hash=v=>createHash('sha256').update(canon(v)).digest('hex')
const eq=(a,b)=>canon(a)===canon(b)
const repo=v=>v?.id===REPO_ID&&v.full_name===REPO
const positive=v=>Number.isSafeInteger(v)&&v>0
const complete=(v,k)=>Number.isSafeInteger(v?.total_count)&&Array.isArray(v[k])&&v.total_count===v[k].length&&v.total_count<=100
function taskBinding(s,id){
 validateSnapshot(s)
 check(s.status==='ACTIVE','RECEIPT_REQUIREMENT_INACTIVE')
 const t=s.tasks.find(t=>t.task_id===id)
 check(t?.status==='IN_REVIEW'&&t.claim&&positive(t.pr_number)&&SHA.test(t.head_sha),'RECEIPT_TASK_NOT_SUBMITTED')
 // Fail closed if any subsequent operation on this task occurred. Unrelated
 // task revisions may proceed. A new submit invalidates earlier receipts.
 const last=s.processed_requests.filter(x=>x.receipt.task_id===id).at(-1)
 check(last?.receipt.type==='submit'&&last.receipt.status==='IN_REVIEW'&&
   last.actor===t.claim.actor&&last.receipt.request_id===last.request_id&&
   positive(last.receipt.version)&&last.receipt.version<=s.version,'RECEIPT_SUBMISSION_MISSING')
 return {requirement_id:s.requirement_id,task_id:id,submit_request_id:last.request_id,
   submit_version:last.receipt.version,lease_fingerprint:hash([t.claim.claim_id,t.claim.worker_id,t.claim.actor,t.claim.generation??1]),
   pr_number:t.pr_number,head_sha:t.head_sha,base_ref:'integrate/'+s.requirement_id}
}
function prBinding(b,p){
 check(p?.number===b.pr_number&&p.head?.sha===b.head_sha&&p.base?.ref===b.base_ref&&repo(p.base.repo)&&repo(p.head.repo)&&
   SHA.test(p.base.sha)&&typeof p.head.ref==='string'&&p.head.ref.length>0,'RECEIPT_PR_MISMATCH')
 return {base_sha:p.base.sha,head_ref:p.head.ref}
}
function mergeObject(c,sha,base,head){
 check(SHA.test(sha)&&c?.sha===sha&&SHA.test(c.tree?.sha)&&
   eq(c.parents?.map(p=>p.sha),[base,head]),'RECEIPT_MERGE_OBJECT')
 return c.tree.sha
}
function workflowBlobs(e){
 check(eq(Object.keys(e??{}).sort(),PATHS.slice().sort())&&PATHS.every(p=>
   Array.isArray(e[p])&&e[p].length===2&&SHA.test(e[p][0])&&e[p][0]===e[p][1]),'RECEIPT_WORKFLOW_DRIFT')
 return Object.fromEntries(PATHS.map(p=>[p,e[p][0]]))
}
function collectChecks(e,b,p,mode){
 const c=e.checks
 check(complete(c,'check_runs'),'RECEIPT_INCOMPLETE_CHECKS')
 const records=[]
 for(const name of REQUIRED_CHECKS){
   const matches=c.check_runs.filter(x=>x.name===name&&x.app?.id===APP_ID&&x.app?.slug==='github-actions')
   check(matches.every(x=>positive(x.id))&&new Set(matches.map(x=>x.id)).size===matches.length,'RECEIPT_CHECK_ID')
   const j=matches.sort((a,b)=>b.id-a.id)[0]
   check(j?.head_sha===b.head_sha&&j.status==='completed'&&j.conclusion==='success','RECEIPT_CHECK_NOT_GREEN')
   const m=j.details_url?.match(/^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
   check(m&&Number(m[2])===j.id&&positive(Number(m[1])),'RECEIPT_CHECK_LINK')
   const id=Number(m[1]),run=e.runs?.[id],list=e.jobs?.[id]
   const path=name==='impact-report'?IMPACT:name==='dev-collab-contract'?CONTRACT:CI
   const workflow=path===IMPACT?'Feature Impact Report':path===CONTRACT?'PRP Dev Collaboration Contract':'CI'
   check(run?.id===id&&run.path===path&&run.name===workflow&&run.event==='pull_request'&&run.status==='completed'&&run.conclusion==='success'&&
     run.head_sha===b.head_sha&&run.head_branch===p.head.ref&&repo(run.repository)&&repo(run.head_repository)&&positive(run.run_attempt),
     'RECEIPT_RUN_MISMATCH')
   const exactPR=x=>x.number===b.pr_number&&x.head?.sha===b.head_sha&&x.base?.ref===b.base_ref&&x.base?.sha===p.base.sha&&
     x.head?.repo?.id===REPO_ID&&x.base?.repo?.id===REPO_ID
   check(Array.isArray(run.pull_requests)&&(mode==='after'&&run.pull_requests.length===0||
     run.pull_requests.length>0&&run.pull_requests.every(exactPR)),'RECEIPT_RUN_PR_MISMATCH')
   check(complete(list,'jobs'),'RECEIPT_INCOMPLETE_JOBS')
   const js=list.jobs.filter(x=>x.id===j.id),job=js[0]
   check(js.length===1&&job.name===name&&job.run_id===id&&job.run_attempt===run.run_attempt&&job.head_sha===b.head_sha&&
     job.status==='completed'&&job.conclusion==='success'&&Number.isFinite(time(job.completed_at))&&
     time(run.created_at)<=time(job.completed_at),'RECEIPT_JOB_MISMATCH')
   records.push({name,check_id:j.id,run_id:id,run_attempt:run.run_attempt,workflow_path:path,completed_at:job.completed_at})
 }
 return records
}
export function capturePremergeReceipt(snapshot,taskId,e,{stateSha,capturedAt}){
 const b=taskBinding(snapshot,taskId),p=e.pr,refs=prBinding(b,p)
 check(SHA.test(stateSha)&&Number.isFinite(time(capturedAt)),'RECEIPT_CAPTURE_CONTEXT')
 check(p.state==='open'&&p.merged===false&&p.draft===false&&p.mergeable===true,'RECEIPT_PR_NOT_READY')
 check(e.branch?.name===b.base_ref&&e.branch.protected===true&&e.branch.commit?.sha===refs.base_sha,'RECEIPT_BASE_MOVED')
 verifyTaskChangedFiles(snapshot.tasks.find(t=>t.task_id===taskId),p,e.files)
 const tree=mergeObject(e.testCommit,p.merge_commit_sha,refs.base_sha,b.head_sha)
 const workflows=workflowBlobs(e.workflowBlobs)
 // Preserve current strict workflow provenance check, then pin exact job IDs.
 verifyWorkflowProvenance(e.checks,{sha:b.head_sha,prNumber:b.pr_number,baseRef:b.base_ref,headRef:refs.head_ref},id=>e.runs[id])
 const checks=collectChecks(e,b,p,'before')
 check(checks.every(x=>time(x.completed_at)<=time(capturedAt)),'RECEIPT_CAPTURE_BEFORE_CI')
 const body={schema_version:1,repository_id:REPO_ID,...b,...refs,state_sha:stateSha,state_version:snapshot.version,captured_at:capturedAt,
   synthetic_merge_sha:p.merge_commit_sha,tree_sha:tree,workflow_blobs:workflows,checks}
 return {body,digest:hash(body)}
}
// IMPORTANT: storedReceipt MUST be independently read from the protected ledger
// by the caller. The local digest only detects accidental corruption.
export function verifyPersistedPremergeReceipt(snapshot,taskId,storedReceipt,e){
 const x=storedReceipt?.body
 check(x?.schema_version===1&&x.repository_id===REPO_ID&&storedReceipt.digest===hash(x),'RECEIPT_CORRUPT')
 const b=taskBinding(snapshot,taskId),p=e.pr,refs=prBinding(b,p)
 check(Object.entries({...b,...refs}).every(([k,v])=>x[k]===v)&&SHA.test(x.state_sha)&&
   positive(x.state_version)&&x.state_version>=b.submit_version&&snapshot.version>=x.state_version,'RECEIPT_STALE_SUBMISSION')
 check(Number.isFinite(time(x.captured_at))&&time(x.captured_at)<time(p.merged_at),'RECEIPT_CAPTURE_NOT_PREMERGE')
 // Retain original merged-PR, scope, branch protection and ancestry gate.
 verifyTaskEvidence(snapshot,taskId,e)
 check(mergeObject(e.testCommit,x.synthetic_merge_sha,refs.base_sha,b.head_sha)===x.tree_sha&&
   mergeObject(e.actualMergeCommit,p.merge_commit_sha,refs.base_sha,b.head_sha)===x.tree_sha,'RECEIPT_TREE_MISMATCH')
 check(eq(workflowBlobs(e.workflowBlobs),x.workflow_blobs),'RECEIPT_WORKFLOW_DRIFT')
 const current=collectChecks(e,b,p,'after')
 check(eq(current,x.checks)&&current.every(j=>time(j.completed_at)<=time(x.captured_at)),'RECEIPT_CHECKS_CHANGED')
 // Evidence-only return. No reviewerAuthorized/ciVerified/merge approval or state mutation.
 return Object.freeze({receiptEvidenceVerified:true,pr_number:b.pr_number,head_sha:b.head_sha,merge_sha:p.merge_commit_sha,checks:current.length})
}
