import test from 'node:test'
import assert from 'node:assert/strict'
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
 repository:{full_name:repo,default_branch:'main',owner:{login:owner}},
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
 reject({...e,issue:{...e.issue,user:{login:owner,id:202}}},'INGRESS_UNTRUSTED_ISSUE')
 reject({...e,issue:{...e.issue,pull_request:{url:'forged'}}},'INGRESS_UNTRUSTED_ISSUE')
 reject(e,'INGRESS_ISSUE_MODIFIED',env(),{...e.issue,body:'{"edited":true}'})
 reject(e,'INGRESS_ISSUE_MODIFIED',env(),{...e.issue,state:'closed'})
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
 reject(e,'INGRESS_CLAIM')
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
 e.issue.body=JSON.stringify({...p,new_worker_id:'chat-old'})
 reject(e,'INGRESS_RECOVERY_FIELDS')
 e.issue.body=JSON.stringify({...p,note:''})
 reject(e,'INGRESS_RECOVERY_FIELDS')
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
