import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {applyAuthenticatedIssue,redactedReceipt,verifyTaskIssue} from './issue-transaction.mjs'
import {validateIssueEvent} from './issue-ingress.mjs'
const sha='a'.repeat(40),req='REQ-20261031-001'
const uuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const snap=()=>({schema_version:1,requirement_id:req,issue_number:132,
 title:'Task registry',status:'ACTIVE',version:0,processed_requests:[],
 tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'READY',
  depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null}]})
const migrated=()=>{
 const s=snap()
 s.version=1
 for(const [number,issue] of [[2,134],[3,135],[4,136],[5,137],[6,141],[7,142],[8,143],[9,146]]){
  s.tasks.push({task_id:'T-'+String(number).padStart(3,'0'),issue_number:issue,
   title:'V1 task '+number,status:'READY',depends_on:[],allowed_paths:[],claim:null})
 }
 return s
}
const v=(action,command={},version=0)=>{
 const value={type:action,requirement_id:req,task_id:'T-001',request_id:uuid,
  worker_id:'chat-A',...command}
 if(['handoff','takeover'].includes(action)&&value.expected_version===undefined)
   value.expected_version=version
 return {expected_version:version,actor:'micor-cjj-spec',
  recoveryAuthorized:action==='takeover',command:value}
}
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
 assert.ok(w.includes('permission-contents: ${{ steps.validate.outputs.app_contents_permission }}'))
 assert.ok(w.includes('oneShotProbe===true?"read":"write"'))
 assert.match(w,/Post redacted success receipt/)
 assert.ok(w.includes('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'))
 assert.ok(w.includes('actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1'))
 assert.ok(w.includes('actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510'))
 assert.ok(w.includes('package-manager-cache: false'))
 assert.ok(!['actions/checkout@v4','actions/setup-node@v4','actions/create-github-app-token@v3'].some(x=>w.includes(x)))
 assert.doesNotMatch(w,/secrets\.GITHUB_TOKEN|pull-requests: write|^\s*contents: write/m)
})

test('full owner Issue -> checkpoint -> handoff -> new chat; stale worker is fenced',()=>{
 const owner='micor-cjj-spec',repo=owner+'/matrix-prp'
 const env={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',
  GITHUB_REF:'refs/heads/main',GITHUB_REPOSITORY:repo,
  GITHUB_REPOSITORY_OWNER:owner,GITHUB_ACTOR:owner,GITHUB_SHA:sha,
  GITHUB_WORKFLOW_REF:repo+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'}
 const issue=(body,number)=>({action:'opened',sender:{login:owner,id:101,type:'User'},
  repository:{full_name:repo,default_branch:'main',owner:{login:owner,id:101}},
  issue:{number,title:'[PRP-COLLAB-REQUEST]',state:'open',
   user:{login:owner,id:101},author_association:'OWNER',body:JSON.stringify(body)}})
 const receive=(payload,n,state)=>{
  const evt=issue(payload,n),parsed=validateIssueEvent(env,evt,evt.issue)
  return applyAuthenticatedIssue(state,parsed,'2026-11-01T03:30:00Z',cp=>cp.head_sha===sha)
 }
 let state=snap()
 const base={schema_version:1,requirement_id:req,task_id:'T-001',worker_id:'chat-A'}
 const claimed=receive({...base,action:'claim',expected_version:0,
  request_id:'11111111-1111-4111-8111-111111111111'},201,state)
 const old=claimed.receipt.claim_id
 state=claimed.snapshot
 const cp={summary:'Pushed feature implementation',
  next_step:'Run CI and inspect reviewed changes',branch:'feat/old-session',
  head_sha:sha,tests:'No CI evidence verified'}
 const checked=receive({...base,action:'checkpoint',expected_version:1,
  request_id:'22222222-2222-4222-8222-222222222222',claim_id:old,
  checkpoint:cp},202,state)
 assert.equal(checked.snapshot.tasks[0].checkpoint.head_sha,sha)
 state=checked.snapshot
 const transferred=receive({...base,action:'handoff',expected_version:2,
  request_id:'33333333-3333-4333-8333-333333333333',claim_id:old,
  new_worker_id:'chat-B',expected_head_sha:sha,
  note:'Former chat is handing off work'},203,state)
 assert.equal(transferred.snapshot.tasks[0].claim.worker_id,'chat-B')
 assert.equal(transferred.snapshot.tasks[0].claim.generation,2)
 const latest=transferred.snapshot.tasks[0].claim.claim_id
 assert.notEqual(latest,old)
 assert.throws(()=>receive({...base,action:'start',expected_version:3,
  request_id:'44444444-4444-4444-8444-444444444444',claim_id:old},204,
  transferred.snapshot),e=>e.code==='STALE_OR_FOREIGN_CLAIM')
 const nextChat=receive({...base,worker_id:'chat-B',action:'start',expected_version:3,
  request_id:'55555555-5555-4555-8555-555555555555',claim_id:latest},205,
  transferred.snapshot)
 assert.equal(nextChat.snapshot.tasks[0].status,'IN_PROGRESS')
})
test('full owner Issue takeover maps the expected state version, not just the outer envelope',()=>{
 const owner='micor-cjj-spec',repo=owner+'/matrix-prp'
 const env={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',
  GITHUB_REF:'refs/heads/main',GITHUB_REPOSITORY:repo,
  GITHUB_REPOSITORY_OWNER:owner,GITHUB_ACTOR:owner,GITHUB_SHA:sha,
  GITHUB_WORKFLOW_REF:repo+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'}
 const first=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:30:00Z')
 const old=first.receipt.claim_id
 const body={schema_version:1,action:'takeover',request_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  requirement_id:req,task_id:'T-001',worker_id:'chat-A',new_worker_id:'chat-B',
  expected_version:1,expected_claim_id:old,expected_head_sha:sha,
  note:'Old chat crashed before a checkpoint',
  checkpoint:{summary:'Recovered remote work from GitHub',next_step:'Inspect next CI run',
   branch:'feat/recovered-work',head_sha:sha}}
 const evt={action:'opened',sender:{login:owner,id:101,type:'User'},
  repository:{full_name:repo,default_branch:'main',owner:{login:owner,id:101}},
  issue:{number:206,title:'[PRP-COLLAB-REQUEST]',state:'open',user:{login:owner,id:101},
   author_association:'OWNER',body:JSON.stringify(body)}}
 const parsed=validateIssueEvent(env,evt,evt.issue)
 assert.equal(parsed.command.expected_version,1)
 const recovered=applyAuthenticatedIssue(first.snapshot,parsed,'2026-11-01T03:40:00Z',
  ()=>true)
 assert.equal(recovered.snapshot.tasks[0].claim.worker_id,'chat-B')
 assert.equal(recovered.snapshot.tasks[0].checkpoint.origin,'owner_verified_git')
 assert.notEqual(recovered.snapshot.tasks[0].claim.claim_id,old)
})

test('checkpoint and handoff both require the exact remote Git branch SHA',()=>{
 const base=snap()
 const claimed=applyAuthenticatedIssue(base,v('claim'),'2026-11-01T03:30:00Z')
 const claim=claimed.receipt.claim_id
 const cp={summary:'Committed work on the old chat branch',
  next_step:'Continue with review and tests',branch:'feat/old-session',head_sha:sha}
 const checkpoint=v('checkpoint',{claim_id:claim,checkpoint:cp},1)
 checkpoint.command.request_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
 assert.throws(()=>applyAuthenticatedIssue(claimed.snapshot,checkpoint,
  '2026-11-01T03:31:00Z',()=>false),e=>e.code==='ISSUE_UNVERIFIED_RECOVERY_HEAD')
 const saved=applyAuthenticatedIssue(claimed.snapshot,checkpoint,
  '2026-11-01T03:31:00Z',()=>true)
 const transfer=v('handoff',{worker_id:'chat-A',claim_id:claim,
  new_worker_id:'chat-B',expected_head_sha:sha,note:'Continue in a fresh chat'},2)
 transfer.command.request_id='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
 assert.throws(()=>applyAuthenticatedIssue(saved.snapshot,transfer,
  '2026-11-01T03:32:00Z',()=>false),e=>e.code==='ISSUE_UNVERIFIED_RECOVERY_HEAD')
 const handed=applyAuthenticatedIssue(saved.snapshot,transfer,
  '2026-11-01T03:32:00Z',()=>true)
 assert.equal(handed.snapshot.tasks[0].claim.worker_id,'chat-B')
 assert.equal(handed.snapshot.tasks[0].checkpoint.head_sha,sha)
})

test('task registry write requires a matching owner-authored task Issue manifest',()=>{
 const command={type:'register_task',requirement_id:req,task_id:'T-002',
  issue_number:151,title:'Add dashboard filtering',depends_on:['T-001'],
  allowed_paths:['app/web/src/']}
 const validated={command,actor:'micor-cjj-spec',actorId:101,source_issue:150}
 const manifest={schema_version:1,requirement_id:req,task_id:'T-002',
  title:command.title,depends_on:command.depends_on,allowed_paths:command.allowed_paths}
 const issue={number:151,title:'[TASK]['+req+'/T-002] '+command.title,
  state:'open',user:{login:'micor-cjj-spec',id:101},author_association:'OWNER',
  body:'Task objective and acceptance criteria\n\n<!-- PRP_TASK_MANIFEST\n'+
   JSON.stringify(manifest)+'\n-->'}
 assert.equal(verifyTaskIssue(issue,validated),true)
 assert.throws(()=>verifyTaskIssue({...issue,user:{login:'attacker',id:202}},validated),
  e=>e.code==='ISSUE_TASK_IDENTITY')
 assert.throws(()=>verifyTaskIssue({...issue,body:issue.body.replace('T-001','T-003')},validated),
  e=>e.code==='ISSUE_TASK_MANIFEST_MISMATCH')
 assert.throws(()=>verifyTaskIssue({...issue,title:'[TASK]['+req+'/T-003] '+command.title},validated),
  e=>e.code==='ISSUE_TASK_IDENTITY')
})
test('register_task is refused without a verified related Issue and records no claim',()=>{
 const state=migrated()
 const command={type:'register_task',requirement_id:req,task_id:'T-010',
  request_id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',issue_number:151,
  title:'Add dashboard filtering',depends_on:['T-001'],allowed_paths:['app/web/src/']}
 const validated={command,actor:'micor-cjj-spec',actorId:101,
  source_issue:150,expected_version:1,taskIssueVerified:false}
 assert.throws(()=>applyAuthenticatedIssue(state,validated,'2026-11-01T03:50:00Z'),
  e=>e.code==='ISSUE_TASK_NOT_VERIFIED')
 const result=applyAuthenticatedIssue(state,{...validated,taskIssueVerified:true},
  '2026-11-01T03:50:00Z')
 assert.equal(result.snapshot.tasks.length,10)
 assert.equal(result.snapshot.tasks[9].task_id,'T-010')
 assert.equal(result.snapshot.tasks[1].status,'READY')
 assert.equal(result.snapshot.tasks[1].claim,null)
 assert.equal(result.receipt.issue_number,151)
 assert.equal(redactedReceipt(result.receipt,{requirement_id:req,state_sha:sha}).task_issue_number,151)
})

test('replayed checkpoint and handoff stay idempotent after their remote branch has moved',()=>{
 const claimed=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:30:00Z')
 const claimId=claimed.receipt.claim_id
 const cp={summary:'Remote branch was committed for recovery',
  next_step:'Hand over to the next conversation',branch:'feat/old-session',head_sha:sha}
 const checkpoint=v('checkpoint',{claim_id:claimId,checkpoint:cp},1)
 checkpoint.command.request_id='11111111-2222-4333-8444-555555555555'
 const saved=applyAuthenticatedIssue(claimed.snapshot,checkpoint,'2026-11-01T03:31:00Z',()=>true)
 let remoteChecks=0
 const moved=()=>{remoteChecks++;return false}
 const retry=applyAuthenticatedIssue(saved.snapshot,checkpoint,'2026-11-01T03:33:00Z',moved)
 assert.strictEqual(retry.snapshot,saved.snapshot)
 assert.equal(retry.receipt.replayed,true)
 assert.equal(remoteChecks,0)
 assert.throws(()=>applyAuthenticatedIssue(saved.snapshot,{
  ...checkpoint,command:{...checkpoint.command,checkpoint:{...cp,summary:'Different checkpoint'}}
 },'2026-11-01T03:33:00Z',moved),e=>e.code==='REQUEST_ID_COLLISION')
 const handoff=v('handoff',{claim_id:claimId,new_worker_id:'chat-B',
  expected_head_sha:sha,note:'Old session handing off work'},2)
 handoff.command.request_id='22222222-3333-4444-8555-666666666666'
 const accepted=applyAuthenticatedIssue(saved.snapshot,handoff,'2026-11-01T03:34:00Z',()=>true)
 const handoffRetry=applyAuthenticatedIssue(accepted.snapshot,handoff,
  '2026-11-01T03:35:00Z',moved)
 assert.strictEqual(handoffRetry.snapshot,accepted.snapshot)
 assert.equal(handoffRetry.receipt.replayed,true)
 assert.equal(remoteChecks,0)
})
test('replayed takeover still validates owner and exact request fingerprint',()=>{
 const a=applyAuthenticatedIssue(snap(),v('claim'),'2026-11-01T03:30:00Z')
 const id=a.receipt.claim_id
 const cmd=v('takeover',{claim_id:id,expected_claim_id:id,
  expected_version:1,new_worker_id:'chat-C',expected_head_sha:sha,
  note:'Old chat cannot continue',
  checkpoint:{summary:'Recovery from committed Git history',
   next_step:'Resume tests in the new chat',branch:'feat/recovered-old-chat',head_sha:sha}},1)
 cmd.command.request_id='33333333-4444-4555-8666-777777777777'
 const accepted=applyAuthenticatedIssue(a.snapshot,cmd,'2026-11-01T03:40:00Z',()=>true)
 const retry=applyAuthenticatedIssue(accepted.snapshot,cmd,'2026-11-01T03:41:00Z',()=>false)
 assert.strictEqual(retry.snapshot,accepted.snapshot)
 assert.equal(retry.receipt.replayed,true)
 assert.throws(()=>applyAuthenticatedIssue(accepted.snapshot,
  {...cmd,actor:'another-user'},'2026-11-01T03:41:00Z',()=>false),
  e=>e.code==='ISSUE_UNTRUSTED_ACTOR')
 assert.throws(()=>applyAuthenticatedIssue(accepted.snapshot,
  {...cmd,command:{...cmd.command,new_worker_id:'chat-D'}},
  '2026-11-01T03:41:00Z',()=>false),e=>e.code==='REQUEST_ID_COLLISION')
})
