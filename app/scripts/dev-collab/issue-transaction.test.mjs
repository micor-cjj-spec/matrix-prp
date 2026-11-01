import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {applyAuthenticatedIssue,redactedReceipt} from './issue-transaction.mjs'
const sha='a'.repeat(40),req='REQ-20261031-001'
const uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const snap=()=>({schema_version:1,requirement_id:req,issue_number:132,
 title:'Task registry',status:'ACTIVE',version:0,processed_requests:[],
 tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'READY',
  depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null}]})
const v=(action,command={},version=0)=>({
 expected_version:version,actor:'micor-cjj-spec',recoveryAuthorized:action==='takeover',
 command:{type:action,requirement_id:req,task_id:'T-001',request_id:uuid,
  worker_id:'chat-A',...command}
})
test('owner request claims exactly once; public receipt never leaks claim ID',()=>{
 const a=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:20:00Z')
 assert.equal(a.snapshot.version,1)
 assert.equal(a.snapshot.tasks[0].status,'CLAIMED')
 const receipt=redactedReceipt(a.receipt,{requirement_id:req,state_sha:sha})
 assert.equal(receipt.version,1)
 assert.equal(receipt.state_sha,sha)
 assert.doesNotMatch(JSON.stringify(receipt),new RegExp(a.receipt.claim_id))
 assert.throws(()=>applyAuthenticatedIssue(snap(),v('claim',{},7),
  '2026-11-01T03:20:00Z'),e=>e.code==='ISSUE_STALE_VERSION')
})
test('replay request ID is idempotent, different commands with same ID fail closed',()=>{
 const a=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:20:00Z')
 const replay=applyAuthenticatedIssue(a.snapshot,v('claim'),'2026-11-01T03:20:00Z')
 assert.strictEqual(replay.snapshot,a.snapshot)
 assert.equal(replay.receipt.replayed,true)
 assert.throws(()=>applyAuthenticatedIssue(a.snapshot,v('start',{},0),
  '2026-11-01T03:20:00Z'),e=>e.code==='REQUEST_ID_COLLISION')
})
test('orphaned chat recovery requires exact Git evidence and rotates old lease',()=>{
 const a=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:20:00Z')
 const old=a.snapshot.tasks[0].claim.claim_id
 const cmd=v('takeover',{worker_id:'chat-A',claim_id:old,expected_claim_id:old,
  expected_version:1,new_worker_id:'chat-B',expected_head_sha:sha,
  note:'Original chat was lost',
  checkpoint:{summary:'Recovered from pushed branch',next_step:'Check GitHub CI',
   branch:'feat/old-chat',head_sha:sha}},1)
 cmd.command.request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
 assert.throws(()=>applyAuthenticatedIssue(a.snapshot,cmd,'2026-11-01T03:30:00Z',()=>false),
  e=>e.code==='ISSUE_UNVERIFIED_RECOVERY_HEAD')
 const done=applyAuthenticatedIssue(a.snapshot,cmd,'2026-11-01T03:30:00Z',()=>true)
 assert.equal(done.snapshot.tasks[0].claim.worker_id,'chat-B')
 assert.equal(done.snapshot.tasks[0].claim.generation,2)
 assert.notEqual(done.snapshot.tasks[0].claim.claim_id,old)
 assert.equal(done.snapshot.tasks[0].checkpoint.origin,'owner_verified_git')
})
test('automation workflow has only owner-opened Issue trigger and an isolated environment',()=>{
 const w=readFileSync(new URL('../../../.github/workflows/prp-collab-issue-ingress.yml',import.meta.url),'utf8')
 assert.match(w,/issues:\s*\n\s*types: \[opened\]/)
 assert.doesNotMatch(w,/issue_comment:|pull_request_target:|schedule:|workflow_dispatch:/)
 assert.match(w,/github\.actor == github\.repository_owner/)
 assert.match(w,/environment: prp-collab-automation/)
 assert.match(w,/issue-ingress\.mjs/)
 assert.match(w,/issue-transaction\.mjs/)
 assert.match(w,/repositories: matrix-prp/)
 assert.match(w,/permission-contents: write/)
 assert.match(w,/Post redacted success receipt/)
 assert.doesNotMatch(w,/secrets\.GITHUB_TOKEN|pull-requests: write|^\s*contents: write/m)
})
