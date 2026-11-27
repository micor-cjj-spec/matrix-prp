// Trusted evidence adapter. Only protected-main Owner Issue transactions call
// this module. No user-supplied evidence or positive review flags are accepted.
import {CollabError,validateSnapshot} from './core.mjs'
import {REQUIRED_CHECKS,verifyTaskChangedFiles,hasDevAncestry,verifyOwnerAttestedIntegrationPolicy} from './review-gate.mjs'
import {verifyInitialReviewCheckout} from './review-provenance.mjs'
import {verifyPersistedPremergeReceipt} from './review-receipt.mjs'
import {receiptPath,parseStoredReceipt,verifyReceiptAppendCommit} from './review-receipt-store.mjs'

const REPO='micor-cjj-spec/matrix-prp',ROOT='repos/'+REPO,REPO_ID=1261866723,OWNER_ID=123868412
const SHA=/^[a-f0-9]{40}$/,UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const PIN='3d3c42e5aac5ba805825da76410c181273ba90b1'
const ISSUE_WORKFLOW='.github/workflows/prp-collab-issue-ingress.yml'
const WORKFLOWS=['.github/workflows/ci.yml','.github/workflows/feature-impact.yml','.github/workflows/prp-dev-collab-contract.yml']
const check=(ok,code)=>{if(!ok)throw new CollabError(code)}
const time=v=>typeof v==='string'?Date.parse(v):NaN
const positive=v=>Number.isSafeInteger(v)&&v>0
const eq=(a,b)=>JSON.stringify(a)===JSON.stringify(b)
const repo=x=>x?.id===REPO_ID&&x.full_name===REPO

export const RECEIPT_ACCEPT_PREFIX='PRP_PREMERGE_RECEIPT_V1:'
export function submittedReceiptPath(snapshot,taskId){
 validateSnapshot(snapshot)
 const t=snapshot.tasks.find(x=>x.task_id===taskId)
 const latest=snapshot.processed_requests.filter(x=>x.receipt.task_id===taskId).at(-1)
 check(snapshot.status==='ACTIVE'&&t?.status==='IN_REVIEW'&&t.claim&&latest?.receipt.type==='submit'&&
   latest.receipt.status==='IN_REVIEW'&&latest.actor===t.claim.actor&&latest.receipt.request_id===latest.request_id,'RECEIPT_SUBMISSION_MISSING')
 return receiptPath({requirement_id:snapshot.requirement_id,task_id:taskId,submit_request_id:latest.request_id})
}

export function verifyReceiptCommand(snapshot,command,proof){
 const t=snapshot.tasks.find(x=>x.task_id===command.task_id)
 check(proof?.actorId===OWNER_ID&&positive(proof.sourceIssue)&&proof.expectedVersion===snapshot.version&&
   SHA.test(proof.stateSha||'')&&proof.stateSha===proof.expectedStateSha&&
   command.requirement_id===snapshot.requirement_id&&UUID.test(command.request_id)&&
   t?.status==='IN_REVIEW'&&t.claim?.actor==='micor-cjj-spec'&&
   t.claim.worker_id===command.worker_id&&t.claim.claim_id===command.claim_id&&
   t.pr_number===command.pr_number&&t.head_sha===command.head_sha,'RECEIPT_COMMAND_BINDING')
 return submittedReceiptPath(snapshot,command.task_id)
}

// Reuse the existing first-checkout parser. All seven jobs must have actually
// checked out the same synthetic merge commit, not just a mutable PR association.
export function collectReceiptEvidence(snapshot,taskId,api,stored=null){
 const t=snapshot.tasks.find(x=>x.task_id===taskId)
 submittedReceiptPath(snapshot,taskId)
 const p=api(ROOT+'/pulls/'+t.pr_number),base='integrate/'+snapshot.requirement_id
 check(p?.number===t.pr_number&&p.head?.sha===t.head_sha&&p.base?.ref===base&&
   repo(p.head.repo)&&repo(p.base.repo)&&SHA.test(p.base.sha)&&SHA.test(p.merge_commit_sha),'RECEIPT_PR_MISMATCH')
 const branch=api(ROOT+'/branches/'+encodeURIComponent(base))
 check(branch?.name===base&&branch.protected===true&&SHA.test(branch.commit?.sha),'RECEIPT_BASE_UNPROTECTED')
 const testSha=stored?stored.body.synthetic_merge_sha:p.merge_commit_sha
 check(SHA.test(testSha),'RECEIPT_TEST_SHA')
 if(!stored)check(p.state==='open'&&p.draft===false&&p.merged===false&&p.mergeable===true&&branch.commit.sha===p.base.sha,'RECEIPT_PR_NOT_READY')
 else check(p.merged===true&&Number.isFinite(time(p.merged_at)),'RECEIPT_PR_NOT_MERGED')
 const files=api(ROOT+'/pulls/'+t.pr_number+'/files?per_page=100')
 verifyTaskChangedFiles(t,p,files)
 const checks=api(ROOT+'/commits/'+t.head_sha+'/check-runs?per_page=100&filter=latest')
 check(Number.isSafeInteger(checks?.total_count)&&checks.total_count<=100&&checks.check_runs?.length===checks.total_count,'RECEIPT_INCOMPLETE_CHECKS')
 const runs={},jobs={}
 for(const name of REQUIRED_CHECKS){
   const matches=checks.check_runs.filter(x=>x.name===name&&x.app?.slug==='github-actions')
   check(matches.every(x=>positive(x.id)),'RECEIPT_CHECK_ID')
   const c=matches.sort((a,b)=>b.id-a.id)[0]
   check(c?.app?.id===15368&&c.head_sha===t.head_sha&&c.status==='completed'&&c.conclusion==='success','RECEIPT_CHECK_NOT_GREEN')
   const url=c.details_url?.match(/^https:\/\/github\.com\/micor-cjj-spec\/matrix-prp\/actions\/runs\/(\d+)\/job\/(\d+)$/)
   check(url&&positive(Number(url[1]))&&Number(url[2])===c.id,'RECEIPT_CHECK_LINK')
   const id=Number(url[1])
   const run=runs[id]??=api(ROOT+'/actions/runs/'+id)
   const list=jobs[id]??=api(ROOT+'/actions/runs/'+id+'/jobs?per_page=100&filter=latest')
   const workflow=name==='impact-report'?WORKFLOWS[1]:name==='dev-collab-contract'?WORKFLOWS[2]:WORKFLOWS[0]
   check(run?.id===id&&run.path===workflow&&run.event==='pull_request'&&run.head_sha===t.head_sha&&
     repo(run.repository)&&repo(run.head_repository)&&run.status==='completed'&&run.conclusion==='success'&&positive(run.run_attempt),'RECEIPT_RUN_MISMATCH')
   check(Number.isSafeInteger(list?.total_count)&&list.total_count<=100&&list.jobs?.length===list.total_count,'RECEIPT_INCOMPLETE_JOBS')
   const js=list.jobs.filter(x=>x.name===name)
   const j=js[0]
   check(js.length===1&&j.id===c.id&&j.run_id===id&&j.run_attempt===run.run_attempt&&j.head_sha===t.head_sha&&
     j.head_branch===p.head.ref&&j.workflow_name===run.name&&j.status==='completed'&&j.conclusion==='success'&&
     Number.isFinite(time(j.started_at))&&Number.isFinite(time(j.completed_at))&&time(run.created_at)<=time(j.started_at)&&
     time(j.started_at)<=time(j.completed_at),'RECEIPT_JOB_MISMATCH')
   const log=api(ROOT+'/actions/jobs/'+j.id+'/logs')
   check(verifyInitialReviewCheckout(log,j,t.pr_number,workflow===WORKFLOWS[0]?'v4':PIN)===testSha,'RECEIPT_TESTED_TREE_MISMATCH')
 }
 const testCommit=api(ROOT+'/git/commits/'+testSha)
 const workflowBlobs=Object.fromEntries(WORKFLOWS.map(path=>{
   const refs=[p.base.sha,testSha,...(stored?[p.merge_commit_sha]:[])]
   const shas=refs.map(ref=>api(ROOT+'/contents/'+path+'?ref='+ref)?.sha)
   check(shas.every(x=>SHA.test(x||'')&&x===shas[0]),'RECEIPT_WORKFLOW_DRIFT')
   return [path,shas.slice(0,2)]
 }))
 const evidence={pr:p,branch,files,checks,runs,jobs,testCommit,workflowBlobs}
 if(stored){
   evidence.actualMergeCommit=api(ROOT+'/git/commits/'+p.merge_commit_sha)
   evidence.comparison=api(ROOT+'/compare/'+p.merge_commit_sha+'...'+branch.commit.sha)
 }
 return evidence
}

function contents(api,path,sha){
 check(SHA.test(sha),'RECEIPT_CONTENT_REF')
 const c=api(ROOT+'/contents/'+path+'?ref='+sha)
 check(c?.type==='file'&&c.path===path&&SHA.test(c.sha)&&c.encoding==='base64'&&
   typeof c.content==='string'&&Number.isSafeInteger(c.size)&&c.size>0&&c.size<=1048576,'RECEIPT_CONTENT_INVALID')
 const bytes=Buffer.from(c.content,'base64')
 check(bytes.length===c.size,'RECEIPT_CONTENT_SIZE')
 return {sha:c.sha,bytes:bytes.toString('utf8')}
}
function ancestry(api,ancestor,head){
 check(SHA.test(ancestor)&&SHA.test(head)&&hasDevAncestry(api(ROOT+'/compare/'+ancestor+'...'+head),ancestor),'RECEIPT_ORIGIN_ANCESTRY')
}
export function receiptAppendMarker(issue,sha,digest){
 check(positive(issue)&&SHA.test(sha)&&/^[a-f0-9]{64}$/.test(digest),'RECEIPT_MARKER_INPUT')
 return 'PRP_COLLAB_RECEIPT_APPEND='+issue+' '+sha+' '+digest
}

// Origin is not inferred from the self-reported captured_at or digest. Require
// a unique append commit on protected state, exact one-file diff, the protected
// source revision, completed owner Issue run and its exact transaction log.
export function verifyReceiptOrigin(snapshot,taskId,stateSha,mainSha,stored,api,cutoff){
 const b=stored.body,origin=b.capture_origin,path=submittedReceiptPath(snapshot,taskId)
 check(receiptPath(b)===path&&SHA.test(b.state_sha)&&origin&&
   Object.keys(origin).sort().join(',')==='issue_created_at,main_sha,request_id,run_id,source_issue'&&
   UUID.test(origin.request_id)&&positive(origin.run_id)&&positive(origin.source_issue)&&SHA.test(origin.main_sha)&&
   Number.isFinite(time(origin.issue_created_at))&&Number.isFinite(time(cutoff)),'RECEIPT_ORIGIN_MISSING')
 const current=contents(api,path,stateSha)
 check(current.bytes===JSON.stringify(stored,null,2)+'\n','RECEIPT_ORIGIN_BYTES')
 const history=api(ROOT+'/commits?sha='+stateSha+'&path='+encodeURIComponent(path)+'&per_page=100')
 check(Array.isArray(history)&&history.length===1&&SHA.test(history[0]?.sha),'RECEIPT_ORIGIN_HISTORY')
 const appendSha=history[0].sha,commit=api(ROOT+'/git/commits/'+appendSha)
 check(commit?.sha===appendSha,'RECEIPT_ORIGIN_COMMIT')
 const delta=api(ROOT+'/compare/'+b.state_sha+'...'+appendSha)
 check(delta?.status==='ahead'&&delta.ahead_by===1&&delta.behind_by===0&&delta.base_commit?.sha===b.state_sha&&delta.merge_base_commit?.sha===b.state_sha,'RECEIPT_ORIGIN_PARENT')
 const appended=contents(api,path,appendSha)
 check(appended.sha===current.sha,'RECEIPT_ORIGIN_BLOB')
 const plan={action:'append',path,expectedStateSha:b.state_sha,digest:stored.digest,bytes:current.bytes}
 verifyReceiptAppendCommit(plan,{commit,parent:b.state_sha,files:delta.files,committedBytes:appended.bytes,remoteBefore:b.state_sha})
 ancestry(api,appendSha,stateSha)
 ancestry(api,origin.main_sha,mainSha)
 // A later unrelated main promotion is fine; a changed trusted capture
 // implementation needs separately reviewed migration, never silent fallback.
 for(const f of [ISSUE_WORKFLOW,'app/scripts/dev-collab/review-receipt-runtime.mjs','app/scripts/dev-collab/issue-transaction.mjs']){
   const sha=api(ROOT+'/contents/'+f+'?ref='+origin.main_sha)?.sha
   check(SHA.test(sha||'')&&api(ROOT+'/contents/'+f+'?ref='+mainSha)?.sha===sha,'RECEIPT_ORIGIN_SOURCE_DRIFT')
 }
 const parent=JSON.parse(contents(api,'requirements/'+b.requirement_id+'.json',b.state_sha).bytes)
 check(parent.version===b.state_version&&submittedReceiptPath(parent,taskId)===path,'RECEIPT_ORIGIN_STATE')
 const t=parent.tasks.find(x=>x.task_id===taskId),currentTask=snapshot.tasks.find(x=>x.task_id===taskId)
 check(eq(t.claim,currentTask.claim)&&t.head_sha===b.head_sha&&t.pr_number===b.pr_number,'RECEIPT_ORIGIN_LEASE')
 const issue=api(ROOT+'/issues/'+origin.source_issue)
 check(issue?.number===origin.source_issue&&issue.user?.id===OWNER_ID&&issue.user?.login==='micor-cjj-spec'&&issue.author_association==='OWNER'&&
   issue.title==='[PRP-COLLAB-REQUEST]'&&!issue.pull_request&&issue.created_at===origin.issue_created_at,'RECEIPT_ORIGIN_ISSUE')
 let request
 try{request=JSON.parse(issue.body)}catch{throw new CollabError('RECEIPT_ORIGIN_ISSUE')}
 check(request?.schema_version===1&&request.action==='capture_receipt'&&request.request_id===origin.request_id&&
   request.requirement_id===b.requirement_id&&request.task_id===taskId&&request.expected_version===b.state_version&&request.expected_state_sha===b.state_sha&&
   request.claim_id===t.claim.claim_id&&request.worker_id===t.claim.worker_id&&request.pr_number===b.pr_number&&request.head_sha===b.head_sha,'RECEIPT_ORIGIN_REQUEST')
 const run=api(ROOT+'/actions/runs/'+origin.run_id)
 check(run?.id===origin.run_id&&run.event==='issues'&&run.path===ISSUE_WORKFLOW&&run.head_branch==='main'&&run.head_sha===origin.main_sha&&
   run.run_attempt===1&&run.actor?.id===OWNER_ID&&run.actor?.login==='micor-cjj-spec'&&repo(run.repository)&&
   run.status==='completed'&&run.conclusion==='success'&&Number.isFinite(time(run.created_at))&&Number.isFinite(time(run.updated_at))&&
   time(run.created_at)>=time(origin.issue_created_at)-30000&&time(run.updated_at)<time(cutoff),'RECEIPT_ORIGIN_RUN')
 const list=api(ROOT+'/actions/runs/'+run.id+'/jobs?per_page=100&filter=latest')
 const j=list?.jobs?.[0]
 const step=j?.steps?.filter(x=>x.name==='Execute one strict Git CAS transaction')
 check(list?.total_count===1&&list.jobs.length===1&&positive(j?.id)&&j.run_id===run.id&&j.run_attempt===1&&
   j.name==='apply-owner-request'&&j.head_sha===origin.main_sha&&j.status==='completed'&&j.conclusion==='success'&&
   Number.isFinite(time(j.completed_at))&&time(j.completed_at)<time(cutoff)&&step?.length===1&&step[0].conclusion==='success'&&
   time(step[0].started_at)<=time(b.captured_at)&&time(b.captured_at)<=time(step[0].completed_at),'RECEIPT_ORIGIN_JOB')
 verifyOwnerAttestedIntegrationPolicy(b.requirement_id,api(ROOT+'/rulesets/28050327'),request.policy_attestation,{
   requestId:origin.request_id,action:'capture_receipt',taskId,prNumber:b.pr_number,headSha:b.head_sha,
   stateVersion:b.state_version,mainSha:origin.main_sha,stateSha:b.state_sha
 },{created_at:origin.issue_created_at},time(b.captured_at))
 const log=api(ROOT+'/actions/jobs/'+j.id+'/logs'),marker=receiptAppendMarker(origin.source_issue,appendSha,stored.digest)
 check(typeof log==='string'&&Buffer.byteLength(log)<=4*1024*1024,'RECEIPT_ORIGIN_LOG')
 const hits=log.split(/\r?\n/).map(x=>x.match(/^(\d{4}-\d\d-\d\dT\S+Z) (.*)$/)).filter(x=>x&&x[2]===marker)
 check(hits.length===1&&time(hits[0][1])>=time(step[0].started_at)&&time(hits[0][1])<=time(step[0].completed_at)+999&&time(hits[0][1])<time(cutoff),'RECEIPT_ORIGIN_MARKER')
 return {receiptOriginVerified:true,appendSha,path,digest:stored.digest}
}

export function loadProtectedReceipt(snapshot,taskId,stateSha,api){
 const path=submittedReceiptPath(snapshot,taskId)
 const stored=parseStoredReceipt(contents(api,path,stateSha).bytes)
 check(receiptPath(stored.body)===path,'RECEIPT_ORIGIN_PATH')
 return stored
}

export function verifyReceiptAccept(snapshot,command,proof,mainSha,api){
 verifyReceiptCommand(snapshot,command,proof)
 const stored=loadProtectedReceipt(snapshot,command.task_id,proof.stateSha,api)
 const e=collectReceiptEvidence(snapshot,command.task_id,api,stored)
 verifyReceiptOrigin(snapshot,command.task_id,proof.stateSha,mainSha,stored,api,e.pr.merged_at)
 return verifyPersistedPremergeReceipt(snapshot,command.task_id,stored,e)
}
