import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {validateIssueEvent} from './issue-ingress.mjs'
const owner='micor-cjj-spec',repo=owner+'/matrix-prp',sha='a'.repeat(40)
const env=()=>({GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'issues',
 GITHUB_EVENT_ACTION:'opened',GITHUB_REF:'refs/heads/main',GITHUB_REPOSITORY:repo,
 GITHUB_REPOSITORY_OWNER:owner,GITHUB_ACTOR:owner,GITHUB_SHA:sha,
 GITHUB_WORKFLOW_REF:repo+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'})
const request=()=>({schema_version:1,action:'claim',
 request_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
 requirement_id:'REQ-20261031-001',task_id:'T-001',
 worker_id:'chat-123',expected_version:1})
const event=()=>({action:'opened',sender:{login:owner,id:101,type:'User'},
 repository:{full_name:repo,default_branch:'main',owner:{login:owner,id:101}},
 issue:{number:149,title:'[PRP-COLLAB-REQUEST]',state:'open',
  user:{login:owner,id:101},author_association:'OWNER',body:JSON.stringify(request())}})
const reject=(e,code,environment=env(),current=null)=>
 assert.throws(()=>validateIssueEvent(environment,e,current),x=>x.code===code)
test('authenticated owner-authored issue opens a strict task claim without workflow clicking',()=>{
 const e=event(),x=validateIssueEvent(env(),e,e.issue)
 assert.equal(x.command.type,'claim')
 assert.equal(x.expected_version,1)
 assert.equal(x.actor,owner)
 assert.equal(x.source_issue,149)
 assert.equal(x.recoveryAuthorized,false)
})
test('unauthorized trigger, issue author, PR, wrong workflow and edited issue fail closed',()=>{
 const e=event()
 reject(e,'INGRESS_UNTRUSTED_RUN',{...env(),GITHUB_ACTOR:'attacker'})
 reject(e,'INGRESS_UNTRUSTED_RUN',{...env(),GITHUB_REF:'refs/heads/evil'})
 reject(e,'INGRESS_UNTRUSTED_RUN',{...env(),GITHUB_EVENT_NAME:'issue_comment'})
 reject(e,'INGRESS_UNTRUSTED_RUN',{...env(),GITHUB_WORKFLOW_REF:'evil'})
 reject({...e,sender:{login:'attacker',id:202,type:'User'}},'INGRESS_UNTRUSTED_ISSUE')
 reject({...e,repository:{...e.repository,owner:{login:owner,id:202}}},'INGRESS_UNTRUSTED_ISSUE')
 reject({...e,issue:{...e.issue,user:{login:owner,id:202}}},'INGRESS_UNTRUSTED_ISSUE')
 reject({...e,issue:{...e.issue,pull_request:{url:'forged'}}},'INGRESS_UNTRUSTED_ISSUE')
 reject(e,'INGRESS_ISSUE_MODIFIED',env(),{...e.issue,body:'{"edited":true}'})
 reject(e,'INGRESS_ISSUE_MODIFIED',env(),{...e.issue,state:'closed'})
 reject(e,'INGRESS_ISSUE_MODIFIED',env(),{...e.issue,author_association:'COLLABORATOR'})
})
test('arbitrary JSON fields, code shell or excessive payload are rejected',()=>{
 const e=event()
 e.issue.body=JSON.stringify({...request(),admin_bypass:true})
 reject(e,'INGRESS_BODY_FIELDS')
 e.issue.body='{"bad":"json",}'
 reject(e,'INGRESS_BODY_NOT_JSON')
 e.issue.body='x'.repeat(5000)
 reject(e,'INGRESS_BODY_SIZE')
 e.issue.body=JSON.stringify({...request(),action:'migrate'})
 reject(e,'INGRESS_REQUIRED')
 e.issue.body=JSON.stringify({...request(),worker_id:'foo; echo pwned'})
 reject(e,'INGRESS_REQUIRED')
 e.issue.body=JSON.stringify({...request(),claim_id:'a'.repeat(36)})
 reject(e,'INGRESS_ACTION_FIELDS')
})
test('takeover requires exact old claim, old Git SHA, explicit reason and stays owner-gated',()=>{
 const e=event();const p={...request(),action:'takeover',worker_id:'chat-old',
 new_worker_id:'chat-new',expected_claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
 expected_head_sha:sha,note:'Original chat became unusable'}
 e.issue.body=JSON.stringify(p)
 const out=validateIssueEvent(env(),e,e.issue)
 assert.equal(out.recoveryAuthorized,true)
 assert.equal(out.command.claim_id,p.expected_claim_id)
 assert.equal(out.command.expected_claim_id,p.expected_claim_id)
 assert.equal(out.command.expected_version,p.expected_version)
 e.issue.body=JSON.stringify({...p,new_worker_id:'chat-old'})
 reject(e,'INGRESS_RECOVERY_FIELDS')
 e.issue.body=JSON.stringify({...p,note:''})
 reject(e,'INGRESS_NOTE')
})
test('progress and checkpoint require existing claim and clean checkpoint schema',()=>{
 const e=event(),p={...request(),action:'progress',note:'Reviewed files'}
 e.issue.body=JSON.stringify(p)
 reject(e,'INGRESS_CLAIM_REQUIRED')
 const cp={summary:'Committed feature code',next_step:'Run the unit tests',
 branch:'feat/task-001',head_sha:sha}
 e.issue.body=JSON.stringify({...request(),action:'checkpoint',
 claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',checkpoint:cp})
 assert.equal(validateIssueEvent(env(),e).command.checkpoint.head_sha,sha)
 e.issue.body=JSON.stringify({...request(),action:'checkpoint',
 claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
 checkpoint:{...cp,origin:'owner_verified_git'}})
 reject(e,'INGRESS_CHECKPOINT_FIELDS')
})

test('one-click-free V0 to V1 request is owner-authenticated and pinned to exact commits',()=>{
 const e=event()
 const raw={schema_version:1,action:'migrate_v1',
  request_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  requirement_id:'REQ-20261031-001',
  expected_state_sha:'062036f7021e215ffbfdcbf5689d207a0549b68b',
  expected_proposal_sha:'fb57656dca6df5f12e083fc0430263b4d88e452d'}
 e.issue.body=JSON.stringify(raw)
 const out=validateIssueEvent(env(),e,e.issue)
 assert.equal(out.oneShotMigration,true)
 assert.equal(out.command.type,'migrate_v1')
 assert.equal(out.command.expected_proposal_sha,raw.expected_proposal_sha)
 const variants=[
  {...raw,expected_proposal_sha:'f'.repeat(40)},
  {...raw,expected_state_sha:'e'.repeat(40)},
  {...raw,task_id:'T-001'},
  {...raw,worker_id:'chat-A'},
  {...raw,action:'migrate_v2'}
 ]
 for(const data of variants){
  e.issue.body=JSON.stringify(data)
  assert.throws(()=>validateIssueEvent(env(),e),x=>
   ['INGRESS_UNAPPROVED_MIGRATION','INGRESS_REQUIRED'].includes(x.code))
 }
})

test('per-action field allowlist prevents smuggling unrelated or migration parameters',()=>{
 const e=event()
 const cases=[
  {...request(),head_sha:sha},
  {...request(),new_worker_id:'chat-next'},
  {...request(),expected_proposal_sha:sha},
  {...request(),action:'start',claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',checkpoint:{}},
  {...request(),action:'progress',claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',note:'Reviewed code',expected_head_sha:sha}
 ]
 for(const data of cases){
  e.issue.body=JSON.stringify(data)
  reject(e,'INGRESS_ACTION_FIELDS')
 }
 const takeover={...request(),action:'takeover',worker_id:'chat-old',
   new_worker_id:'chat-new',expected_version:12,expected_head_sha:sha,
   note:'Recover task from broken old session',
   expected_claim_id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
   claim_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc'}
 e.issue.body=JSON.stringify(takeover)
 reject(e,'INGRESS_TAKEOVER_EXPECTED_CLAIM')
})

test('owner Issue can request registration of a separately authored task Issue',()=>{
 const e=event()
 const data={schema_version:1,action:'register_task',
  request_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  requirement_id:'REQ-20261031-001',task_id:'T-010',worker_id:'chat-new',
  expected_version:9,issue_number:151,title:'Add dashboard filtering',
  depends_on:['T-009'],allowed_paths:['app/web/src/','app/backend/src/main/java/']}
 e.issue.body=JSON.stringify(data)
 const out=validateIssueEvent(env(),e,e.issue)
 assert.equal(out.command.type,'register_task')
 assert.equal(out.command.issue_number,151)
 assert.deepEqual(out.command.depends_on,['T-009'])
 assert.deepEqual(out.command.allowed_paths,data.allowed_paths)
 assert.equal(out.actorId,101)
 assert.equal(out.expected_version,9)
})
test('task registration rejects reserved scopes, malformed dependencies and hidden credentials',()=>{
 const e=event()
 const base={schema_version:1,action:'register_task',
  request_id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  requirement_id:'REQ-20261031-001',task_id:'T-010',worker_id:'chat-new',
  expected_version:9,issue_number:151,title:'Add dashboard filtering',
  depends_on:[],allowed_paths:['app/web/src/']}
 for(const data of [
  {...base,allowed_paths:['.github/workflows/']},
  {...base,allowed_paths:['app/scripts/dev-collab/']},
  {...base,allowed_paths:['app/docs/']},
  {...base,depends_on:['T-XYZ']},
  {...base,depends_on:['T-001','T-001']},
  {...base,claim_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'},
  {...base,allowed_paths:['app/web/src/','app/web/src/views/']}
 ]){
  e.issue.body=JSON.stringify(data)
  reject(e,data.claim_id?'INGRESS_ACTION_FIELDS':
    (data.depends_on.some(x=>!/^T-[0-9]{3}$/.test(x))||
     new Set(data.depends_on).size!==data.depends_on.length
      ?'INGRESS_TASK_DEPENDENCIES':'INGRESS_TASK_SCOPE'))
 }
})

test('Issue ingress workflow filters request Issues and mints its writer only after validation',()=>{
 const workflow=readFileSync(new URL('../../../.github/workflows/prp-collab-issue-ingress.yml',import.meta.url),'utf8')
 assert.match(workflow,/issues:\s*\n\s+types:\s*\[opened\]/)
 assert.match(workflow,/github\.event\.issue\.title == '\[PRP-COLLAB-REQUEST\]'/)
 assert.match(workflow,/github\.event\.issue\.author_association == 'OWNER'/)
 assert.match(workflow,/github\.event\.issue\.pull_request == null/)
 assert.match(workflow,/environment: prp-collab-automation/)
 assert.match(workflow,/repositories: matrix-prp/)
 assert.match(workflow,/permission-contents: write/)
 assert.match(workflow,/queue: max/)
 assert.doesNotMatch(workflow,/workflow_dispatch:|pull_request_target:|actions:\s*write/)
 const validation=workflow.indexOf('Validate original GitHub event against current Issue')
 const token=workflow.indexOf('Mint repository-scoped writer token after event validation')
 const transaction=workflow.indexOf('Execute one strict Git CAS transaction')
 assert.ok(validation>=0&&token>validation&&transaction>token)
})

test('owner Issue read-only probe accepts only an exact four-field payload',()=>{
 const e=event()
 const request={schema_version:1,action:'probe',
   request_id:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
   requirement_id:'REQ-20261031-001'}
 e.issue.body=JSON.stringify(request)
 const parsed=validateIssueEvent(env(),e,e.issue)
 assert.equal(parsed.oneShotProbe,true)
 assert.equal(parsed.command.type,'probe')
 assert.equal(parsed.recoveryAuthorized,false)
 assert.equal(parsed.source_issue,149)
 for(const payload of [
   {...request,task_id:'T-001'},
   {...request,expected_version:0},
   {...request,claim_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'},
   {...request,requirement_id:'REQ-20261031-002'},
   {...request,request_id:'not-a-uuid'}
 ]){
   e.issue.body=JSON.stringify(payload)
   reject(e,'INGRESS_UNAPPROVED_PROBE')
 }
})
