import test from 'node:test'
import assert from 'node:assert/strict'
import {capturePremergeReceipt,verifyPersistedPremergeReceipt} from './review-receipt.mjs'
import {REQUIRED_CHECKS} from './review-gate.mjs'
const H='a'.repeat(40),B='b'.repeat(40),T='c'.repeat(40),M='d'.repeat(40),TREE='e'.repeat(40),S='f'.repeat(40)
const R={id:1261866723,full_name:'micor-cjj-spec/matrix-prp'},target='integrate/REQ-20261031-001',head='feat/t001',req='REQ-20261031-001',task='T-001'
const request='22222222-2222-4222-8222-222222222222',claim='11111111-1111-4111-8111-111111111111'
const ci='.github/workflows/ci.yml',impact='.github/workflows/feature-impact.yml',contract='.github/workflows/prp-dev-collab-contract.yml'
const completed='2026-11-25T06:00:00Z',captured='2026-11-25T06:01:00Z',merged='2026-11-25T06:02:00Z'
const make=()=>({schema_version:1,requirement_id:req,issue_number:132,status:'ACTIVE',version:3,title:'MVP',tasks:[{task_id:task,issue_number:133,title:'Core',status:'IN_REVIEW',claim:{claim_id:claim,worker_id:'chat-A',actor:'micor-cjj-spec',generation:1},depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],pr_number:138,head_sha:H}],processed_requests:[{request_id:request,fingerprint:'a'.repeat(64),actor:'micor-cjj-spec',receipt:{type:'submit',task_id:task,request_id:request,version:3,status:'IN_REVIEW'}}]})
const commit=sha=>({sha,tree:{sha:TREE},parents:[{sha:B},{sha:H}]})
function pre(){
 const e={pr:{number:138,state:'open',merged:false,draft:false,mergeable:true,merge_commit_sha:T,changed_files:1,base:{ref:target,sha:B,repo:R},head:{ref:head,sha:H,repo:R}},
   branch:{name:target,protected:true,commit:{sha:B}},testCommit:commit(T),files:[{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}],
   workflowBlobs:Object.fromEntries([ci,impact,contract].map(p=>[p,[S,S]])),checks:{total_count:7,check_runs:[]},runs:{},jobs:{}}
 REQUIRED_CHECKS.forEach((name,i)=>{
   const id=i+100,runId=name==='impact-report'?2:name==='dev-collab-contract'?3:1,path=runId===1?ci:runId===2?impact:contract
   const workflow=runId===1?'CI':runId===2?'Feature Impact Report':'PRP Dev Collaboration Contract'
   e.checks.check_runs.push({id,name,head_sha:H,status:'completed',conclusion:'success',app:{id:15368,slug:'github-actions'},details_url:'https://github.com/'+R.full_name+'/actions/runs/'+runId+'/job/'+id})
   e.runs[runId]={id:runId,path,name:workflow,event:'pull_request',status:'completed',conclusion:'success',head_sha:H,head_branch:head,repository:R,head_repository:R,run_attempt:1,created_at:'2026-11-25T05:59:00Z',pull_requests:[{number:138,head:{sha:H,repo:{id:R.id}},base:{ref:target,sha:B,repo:{id:R.id}}}]}
   const list=e.jobs[runId]??={total_count:0,jobs:[]};list.jobs.push({id,name,run_id:runId,run_attempt:1,head_sha:H,status:'completed',conclusion:'success',completed_at:completed});list.total_count++
 })
 return e
}
function post(){
 const e=pre();e.pr={...e.pr,state:'closed',merged:true,merged_at:merged,merge_commit_sha:M};e.branch.commit.sha=M;e.actualMergeCommit=commit(M)
 e.comparison={status:'identical',behind_by:0,base_commit:{sha:M},merge_base_commit:{sha:M},commits:[]}
 Object.values(e.runs).forEach(r=>r.pull_requests=[])
 return e
}
const capture=(s=make(),e=pre(),at=captured)=>capturePremergeReceipt(s,task,e,{stateSha:S,capturedAt:at})
const fails=f=>assert.throws(f)
test('strict premerge receipt supports empty postmerge association without mutating state',()=>{
 const s=make(),old=structuredClone(s),r=capture(s),result=verifyPersistedPremergeReceipt(s,task,r,post())
 assert.equal(result.receiptEvidenceVerified,true);assert.equal(result.checks,7);assert.equal(result.reviewerAuthorized,undefined);assert.deepEqual(s,old)
 assert.equal(JSON.stringify(r).includes(claim),false)
})
test('unrelated version advance is permitted, same-task resubmission is not',()=>{
 const r=capture(),s=make();s.version=4
 assert.equal(verifyPersistedPremergeReceipt(s,task,r,post()).receiptEvidenceVerified,true)
 s.processed_requests.push({...s.processed_requests[0],request_id:'33333333-3333-4333-8333-333333333333',receipt:{...s.processed_requests[0].receipt,request_id:'33333333-3333-4333-8333-333333333333',version:4}})
 fails(()=>verifyPersistedPremergeReceipt(s,task,r,post()))
})
for(const [label,mutate] of [
 ['already merged',e=>e.pr.merged=true],['draft',e=>e.pr.draft=true],['wrong base',e=>e.pr.base.ref='dev'],['foreign repo',e=>e.pr.head.repo={id:5,full_name:'other/repo'}],
 ['moved integration',e=>e.branch.commit.sha=S],['unprotected integration',e=>e.branch.protected=false],
 ['wrong merge parent',e=>e.testCommit.parents[1].sha=S],['changed workflow',e=>e.workflowBlobs[ci][1]=B],
 ['absent premerge association',e=>e.runs[1].pull_requests=[]],['same head wrong target',e=>e.runs[1].pull_requests[0].base.ref='dev'],
 ['wrong base revision',e=>e.runs[1].pull_requests[0].base.sha=S],['wrong run repository',e=>e.runs[1].repository={id:5,full_name:R.full_name}],
 ['missing jobs',e=>e.jobs[1].total_count++],['stale attempt',e=>e.jobs[1].jobs[0].run_attempt=2],
 ['newer red check',e=>{e.checks.check_runs.push({...e.checks.check_runs[0],id:999,conclusion:'failure'});e.checks.total_count++}],
 ['out of scope file',e=>e.files[0].filename='app/web/src/App.vue']
])test('capture rejects '+label,()=>{const e=pre();mutate(e);fails(()=>capture(make(),e))})
for(const [label,mutate] of [
 ['wrong actual merge parent',e=>e.actualMergeCommit.parents[0].sha=S],['different merged tree',e=>e.actualMergeCommit.tree.sha=S],
 ['not ancestor',e=>e.comparison.behind_by=1],['postmerge workflow drift',e=>e.workflowBlobs[ci][1]=B],
 ['conflicting nonempty association',e=>e.runs[1].pull_requests=[{number:999}]],
 ['new run attempt',e=>{e.runs[1].run_attempt=2;e.jobs[1].jobs.forEach(j=>j.run_attempt=2)}],
 ['new green check ID',e=>{const j=e.checks.check_runs[0];j.id=999;j.details_url=j.details_url.replace(/\/job\/\d+$/,'/job/999');e.jobs[1].jobs[0].id=999}],
 ['unmerged',e=>e.pr.merged=false]
])test('postmerge rejects '+label,()=>{const e=post();mutate(e);fails(()=>verifyPersistedPremergeReceipt(make(),task,capture(),e))})
test('wrong lease or tampered receipt fails',()=>{
 const s=make();s.tasks[0].claim.generation=2;fails(()=>verifyPersistedPremergeReceipt(s,task,capture(),post()))
 const r=capture();r.body.tree_sha=S;fails(()=>verifyPersistedPremergeReceipt(make(),task,r,post()))
})
test('receipt must be captured after checks and before merge',()=>{
 fails(()=>capture(make(),pre(),'2026-11-25T05:58:00Z'))
 const r=capture(make(),pre(),'2026-11-25T06:03:00Z');fails(()=>verifyPersistedPremergeReceipt(make(),task,r,post()))
})
