import test from 'node:test'
import assert from 'node:assert/strict'
import {applyCommand,validateSnapshot,CollabError} from './core.mjs'
import {trustedRecoveryContext} from './recovery-auth.mjs'

const REQ='REQ-20261031-001'
let n=0
const uuid=()=> 'fa120000-0000-4000-8000-'+String(++n).padStart(12,'0')
const owner={actor:'micor-cjj-spec',now:'2026-11-01T02:00:00Z'}
const sha='a'.repeat(40)
const make=()=>({
 schema_version:1,requirement_id:REQ,issue_number:132,title:'Recovery',
 status:'ACTIVE',version:0,processed_requests:[],
 tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'READY',
 depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null}]
})
const command=(type,extras={})=>({
 type,task_id:'T-001',requirement_id:REQ,request_id:uuid(),...extras
})
const fail=(fn,code)=>assert.throws(fn,e=>e instanceof CollabError&&e.code===code)
function running(){
 let state=make()
 const c=applyCommand(state,command('claim',{worker_id:'chat-A'}),owner)
 state=c.snapshot
 const old=c.receipt.claim_id
 state=applyCommand(state,command('start',{worker_id:'chat-A',claim_id:old}),owner).snapshot
 return {state,old}
}
function checkpoint(s,claim,extras={}){
 return applyCommand(s,command('checkpoint',{worker_id:'chat-A',claim_id:claim,
 checkpoint:{summary:'Implemented endpoint and tests',next_step:'Verify branch and review PR',
 branch:'feature/task-001',head_sha:sha,tests:'Node tests passed locally',
 pr_number:222,...extras}}),owner)
}
test('checkpoint needs current claimant; stores concise durable Git-linked progress',()=>{
 const {state,old}=running()
 const c=checkpoint(state,old)
 assert.equal(c.snapshot.tasks[0].checkpoint.head_sha,sha)
 assert.equal(c.snapshot.tasks[0].checkpoint.worker_id,'chat-A')
 assert.equal(c.snapshot.tasks[0].status,'IN_PROGRESS')
 assert.equal(c.receipt.checkpoint_head_sha,sha)
 fail(()=>checkpoint(c.snapshot,uuid()),'STALE_OR_FOREIGN_CLAIM')
})
test('malformed or fake checkpoint paths and reserved metadata are rejected',()=>{
 const {state,old}=running()
 for(const cp of [
 {summary:'okay',next_step:'continue',branch:'../main',head_sha:sha},
 {summary:'okay',next_step:'continue',branch:'feature/something',head_sha:'garbage'},
 {summary:'okay',next_step:'continue',branch:'feature/one',head_sha:sha,recorded_at:'2022-01-01'},
 {summary:'okay',next_step:'continue',branch:'feature/one',head_sha:sha,extra:'not allowed'},
 {summary:'bad\nSECRET',next_step:'continue',branch:'feature/one',head_sha:sha}
 ]){
  assert.throws(()=>applyCommand(state,command('checkpoint',
   {worker_id:'chat-A',claim_id:old,checkpoint:cp}),owner))
 }
})
test('voluntary handoff preserves progress, rotates claim and fences original session',()=>{
 const {state,old}=running()
 const before=checkpoint(state,old).snapshot
 const cmd=command('handoff',{worker_id:'chat-A',claim_id:old,new_worker_id:'chat-B',
  expected_version:before.version,expected_head_sha:sha,note:'The conversation has reached the context limit'})
 const next=applyCommand(before,cmd,owner)
 const task=next.snapshot.tasks[0]
 assert.equal(task.status,'IN_PROGRESS')
 assert.equal(task.claim.worker_id,'chat-B')
 assert.equal(task.claim.generation,2)
 assert.notEqual(task.claim.claim_id,old)
 assert.equal(task.checkpoint.head_sha,sha)
 assert.equal(task.handoff_history[0].type,'handoff')
 fail(()=>applyCommand(next.snapshot,command('progress',
  {worker_id:'chat-A',claim_id:old,note:'lost work'}),owner),'STALE_OR_FOREIGN_CLAIM')
 const replay=applyCommand(next.snapshot,cmd,owner)
 assert.equal(replay.receipt.claim_id,task.claim.claim_id)
 assert.equal(replay.receipt.replayed,true)
 assert.equal(replay.snapshot.version,next.snapshot.version)
 const resumed=applyCommand(next.snapshot,command('progress',
  {worker_id:'chat-B',claim_id:task.claim.claim_id,note:'Continuing validated checkpoint'}),owner)
 assert.equal(resumed.snapshot.tasks[0].last_note,'Continuing validated checkpoint')
})
test('unauthorized takeover fails, owner-authorized takeover works without old chat',()=>{
 const {state,old}=running()
 const before=checkpoint(state,old).snapshot
 const base={worker_id:'chat-A',new_worker_id:'chat-B',expected_claim_id:old,
 expected_version:before.version,expected_head_sha:sha,
 note:'Original GPT conversation is unavailable'}
 fail(()=>applyCommand(before,command('takeover',base),owner),'RECOVERY_OWNER_APPROVAL_REQUIRED')
 const changed=applyCommand(before,command('takeover',base),
  {...owner,recoveryAuthorized:true})
 const task=changed.snapshot.tasks[0]
 assert.equal(task.claim.worker_id,'chat-B')
 assert.equal(task.claim.generation,2)
 assert.equal(task.status,'IN_PROGRESS')
 assert.equal(task.checkpoint.summary,'Implemented endpoint and tests')
 fail(()=>applyCommand(changed.snapshot,command('progress',
  {worker_id:'chat-A',claim_id:old,note:'stale writer'}),owner),'STALE_OR_FOREIGN_CLAIM')
 fail(()=>applyCommand(changed.snapshot,command('takeover',base),
  {...owner,recoveryAuthorized:true}),'STALE_RECOVERY_VERSION')
})
test('stale version, old-claim mismatch and stale SHA reject takeover',()=>{
 const {state,old}=running()
 const s=checkpoint(state,old).snapshot
 const base={worker_id:'chat-A',new_worker_id:'chat-B',
 expected_claim_id:old,expected_version:s.version,expected_head_sha:sha,
 note:'Explicit owner-led recovery'}
 const ctx={...owner,recoveryAuthorized:true}
 fail(()=>applyCommand(s,command('takeover',{...base,expected_version:s.version-1}),ctx),'STALE_RECOVERY_VERSION')
 fail(()=>applyCommand(s,command('takeover',{...base,expected_claim_id:uuid()}),ctx),'STALE_RECOVERY_CLAIM')
 fail(()=>applyCommand(s,command('takeover',{...base,expected_head_sha:'b'.repeat(40)}),ctx),'STALE_RECOVERY_HEAD')
 fail(()=>applyCommand(s,command('handoff',{...base,claim_id:uuid()}),owner),'STALE_OR_FOREIGN_CLAIM')
})
test('cannot take over an uncheckpointed task or seize a completed task',()=>{
 const {state,old}=running()
 const cmd=command('takeover',{worker_id:'chat-A',new_worker_id:'chat-B',
  expected_version:state.version,expected_claim_id:old,expected_head_sha:sha,
  note:'Lost original conversation'})
 fail(()=>applyCommand(state,cmd,{...owner,recoveryAuthorized:true}),'RECOVERY_CHECKPOINT_REQUIRED')
 const s=checkpoint(state,old).snapshot
 s.tasks[0].status='DONE';s.tasks[0].claim=null
 fail(()=>applyCommand(s,cmd,{...owner,recoveryAuthorized:true}),'NOT_CLAIMED')
})
test('handoff cannot silently accept existing review or erase PR provenance',()=>{
 const {state,old}=running()
 let s=applyCommand(state,command('submit',{worker_id:'chat-A',
  claim_id:old,pr_number:222,head_sha:sha}),owner).snapshot
 s=checkpoint(s,old).snapshot
 const result=applyCommand(s,command('handoff',{worker_id:'chat-A',claim_id:old,
  new_worker_id:'chat-B',expected_version:s.version,expected_head_sha:sha,
  note:'Transfer reviewer handoff safely'}),owner)
 const t=result.snapshot.tasks[0]
 assert.equal(t.status,'IN_REVIEW')
 assert.equal(t.pr_number,222)
 assert.equal(t.head_sha,sha)
 fail(()=>applyCommand(result.snapshot,command('accept',
  {pr_number:222,head_sha:sha}),owner),'REVIEW_EVIDENCE_REQUIRED')
 validateSnapshot(result.snapshot)
})
test('takeover event authorization requires trusted GitHub manual main owner workflow',()=>{
 const good={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',
 GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_REF:'refs/heads/main',
 GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-coordinator.yml@refs/heads/main',
 GITHUB_ACTOR:'micor-cjj-spec',GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',GITHUB_SHA:sha}
 assert.deepEqual(trustedRecoveryContext(good),{recoveryAuthorized:true})
 for(const bad of [
  {GITHUB_EVENT_NAME:'pull_request'},
  {GITHUB_REF:'refs/heads/feature'},
  {GITHUB_ACTOR:'external'},
  {GITHUB_ACTIONS:'false'},
  {GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/ci.yml@refs/heads/main'},
  {GITHUB_REPOSITORY:'other/repo'},
  {GITHUB_SHA:'bad'}
 ])fail(()=>trustedRecoveryContext({...good,...bad}),'UNTRUSTED_RECOVERY_CONTEXT')
})
