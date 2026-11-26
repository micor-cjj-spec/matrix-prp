import test from 'node:test'
import assert from 'node:assert/strict'
import {planReceiptAppend,parseStoredReceipt,verifyReceiptAppendCommit,receiptPath} from './review-receipt-store.mjs'
import {REQUIRED_CHECKS} from './review-gate.mjs'
import {execFileSync} from 'node:child_process'
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join,dirname} from 'node:path'
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
   const list=e.jobs[runId]??={total_count:0,jobs:[]};list.jobs.push({id,name,run_id:runId,run_attempt:1,head_sha:H,head_branch:head,workflow_name:workflow,status:'completed',conclusion:'success',started_at:'2026-11-25T05:59:10Z',completed_at:completed});list.total_count++
 })
 return e
}
function post(){
 const e=pre();e.pr={...e.pr,state:'closed',merged:true,merged_at:merged,merge_commit_sha:M};e.branch.commit.sha=M;e.actualMergeCommit=commit(M)
 e.comparison={status:'identical',behind_by:0,base_commit:{sha:M},merge_base_commit:{sha:M},commits:[]}
 Object.values(e.runs).forEach(r=>r.pull_requests=[])
 return e
}

const plan=(opts={})=>planReceiptAppend({snapshot:make(),taskId:task,evidence:pre(),capturedAt:captured,expectedStateSha:S,observedStateSha:S,...opts})
test('receipt path binds exact submit; no claim secret or state mutation',()=>{
 const s=make(),before=structuredClone(s),p=plan({snapshot:s})
 assert.equal(p.action,'append');assert.equal(p.path,'receipts/'+req+'/'+task+'/'+request+'.json')
 assert.equal(parseStoredReceipt(p.bytes).digest,p.digest);assert.equal(p.bytes.includes(claim),false)
 assert.deepEqual(s,before)
})
test('same semantic evidence is idempotent across unrelated state revision',()=>{
 const a=plan(),s=make();s.version++
 const b=plan({snapshot:s,expectedStateSha:B,observedStateSha:B,existingBytes:a.bytes,capturedAt:'2026-11-25T06:01:30Z'})
 assert.equal(b.action,'replay');assert.equal(b.bytes,a.bytes);assert.equal(b.digest,a.digest)
})
test('stale state, unsafe path, corrupted data and changed CI deny append',()=>{
 assert.throws(()=>plan({observedStateSha:B}),/STORE_STALE_STATE/)
 assert.throws(()=>receiptPath({requirement_id:'../oops',task_id:task,submit_request_id:request}),/STORE_PATH_INVALID/)
 const a=plan();assert.throws(()=>plan({existingBytes:a.bytes.replace(TREE,S)}),/STORE_DIGEST_INVALID/)
 const e=pre();e.runs[1].run_attempt=2;e.jobs[1].jobs.forEach(j=>j.run_attempt=2)
 assert.throws(()=>plan({existingBytes:a.bytes,evidence:e}),/STORE_IMMUTABLE_CONFLICT/)
})
test('commit envelope permits exactly one new receipt file and one parent',()=>{
 const a=plan(),env={commit:{sha:M,parents:[{sha:S}]},parent:S,remoteBefore:S,files:[{filename:a.path,status:'added'}],committedBytes:a.bytes}
 assert.equal(verifyReceiptAppendCommit(a,env).appendEnvelopeVerified,true)
 for(const x of [{...env,files:[...env.files,{filename:'requirements/'+req+'.json',status:'modified'}]},
   {...env,files:[{filename:a.path,status:'modified'}]},{...env,commit:{sha:M,parents:[{sha:S},{sha:B}]}},
   {...env,remoteBefore:B},{...env,committedBytes:a.bytes+' '}])assert.throws(()=>verifyReceiptAppendCommit(a,x))
})
function git(cwd,...args){return execFileSync('git',args,{cwd,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim()}
test('real isolated bare Git non-force CAS rejects stale receipt writer; retry preserves independent update',()=>{
 const root=mkdtempSync(join(tmpdir(),'collab-receipt-cas-'))
 try{
  const remote=join(root,'remote.git'),a=join(root,'a'),b=join(root,'b')
  git(root,'init','--bare',remote);git(root,'clone',remote,a)
  git(a,'config','user.name','offline test');git(a,'config','user.email','test@example.invalid')
  git(a,'checkout','-b','prp-collab-state')
  const stateFile='requirements/'+req+'.json'
  mkdirSync(dirname(join(a,stateFile)),{recursive:true});writeFileSync(join(a,stateFile),JSON.stringify(make()))
  git(a,'add','--',stateFile);git(a,'commit','-m','synthetic seed');git(a,'push','origin','HEAD:refs/heads/prp-collab-state')
  const start=git(a,'rev-parse','HEAD')
  git(root,'clone','--branch','prp-collab-state',remote,b)
  git(b,'config','user.name','offline test');git(b,'config','user.email','test@example.invalid')
  const first=plan({expectedStateSha:start,observedStateSha:start})
  mkdirSync(dirname(join(a,first.path)),{recursive:true});writeFileSync(join(a,first.path),first.bytes,{flag:'wx'})
  git(a,'add','--',first.path);git(a,'commit','-m','offline receipt')
  const next=make();next.version=4
  writeFileSync(join(b,stateFile),JSON.stringify(next));git(b,'add','--',stateFile);git(b,'commit','-m','independent synthetic state change');git(b,'push','origin','HEAD:refs/heads/prp-collab-state')
  const winner=git(b,'rev-parse','HEAD')
  assert.throws(()=>git(a,'push','origin','HEAD:refs/heads/prp-collab-state'))
  assert.equal(git(root,'--git-dir='+remote,'rev-parse','refs/heads/prp-collab-state'),winner)
  git(a,'fetch','origin','prp-collab-state');git(a,'reset','--hard','FETCH_HEAD')
  const retry=plan({snapshot:JSON.parse(readFileSync(join(a,stateFile),'utf8')),expectedStateSha:winner,observedStateSha:winner})
  mkdirSync(dirname(join(a,retry.path)),{recursive:true});writeFileSync(join(a,retry.path),retry.bytes,{flag:'wx'})
  git(a,'add','--',retry.path);git(a,'commit','-m','offline receipt after fresh read')
  const sha=git(a,'rev-parse','HEAD'),parents=git(a,'show','-s','--format=%P',sha).split(' ')
  assert.equal(verifyReceiptAppendCommit(retry,{commit:{sha,parents:parents.map(sha=>({sha}))},parent:winner,remoteBefore:winner,
    files:git(a,'diff-tree','--no-commit-id','--name-status','-r',sha).split('\n').map(l=>({status:l.startsWith('A\t')?'added':'other',filename:l.split('\t')[1]})),
    committedBytes:readFileSync(join(a,retry.path),'utf8')}).appendEnvelopeVerified,true)
  git(a,'push','origin','HEAD:refs/heads/prp-collab-state')
  assert.equal(git(root,'--git-dir='+remote,'rev-parse','refs/heads/prp-collab-state'),sha)
  assert.equal(JSON.parse(git(root,'--git-dir='+remote,'show',sha+':'+stateFile)).version,4)
  assert.equal(parseStoredReceipt(git(root,'--git-dir='+remote,'show',sha+':'+retry.path)+'\n').digest,retry.digest)
 }finally{rmSync(root,{recursive:true,force:true})}
})
