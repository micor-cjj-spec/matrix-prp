import test from 'node:test'
import assert from 'node:assert/strict'
import { trustedReviewContext } from './review-context.mjs'
import { HISTORICAL_529_PREFIX } from './review-provenance.mjs'
import { REQUIRED_CHECKS, buildOwnerRulesetAttestation } from './review-gate.mjs'
const req='REQ-20261031-001',sha='a'.repeat(40),merge='b'.repeat(40),branchSha='c'.repeat(40)
const ctx={GITHUB_ACTIONS:'true',GITHUB_REF:'refs/heads/main',
 GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_ACTOR:'micor-cjj-spec',
 GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',GH_TOKEN:'synthetic-test-token',GITHUB_SHA:branchSha,
 GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-coordinator.yml@refs/heads/main'}
const state=()=>({schema_version:1,requirement_id:req,issue_number:132,title:'MVP',
 version:1,status:'ACTIVE',processed_requests:[],
 tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'IN_REVIEW',depends_on:[],
 allowed_paths:['app/scripts/dev-collab/'],claim:{claim_id:'11111111-1111-4111-8111-111111111111',actor:'micor-cjj-spec',worker_id:'chat-A'},
 pr_number:138,head_sha:sha}]})
const checks={total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
 name,id:i+1,head_sha:sha,status:'completed',conclusion:'success',
 details_url:'https://github.com/micor-cjj-spec/matrix-prp/actions/runs/'+(name==='impact-report'?102:name==='dev-collab-contract'?103:101)+'/job/'+(i+1),
 started_at:'2026-10-31T18:00:00Z',app:{slug:'github-actions',id:15368}
}))}
const fakeRun = (route,baseRef,headRef,prNumber)=>{
 const id=Number(route.split('/').pop())
 const names={101:['CI','.github/workflows/ci.yml'],
   102:['Feature Impact Report','.github/workflows/feature-impact.yml'],
   103:['PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']}
 const [name,path]=names[id]||[]
 return {id,name,path,run_attempt:2,created_at:'2026-10-31T17:00:00Z',event:'pull_request',status:'completed',conclusion:'success',head_sha:sha,
  head_branch:headRef,repository:{full_name:'micor-cjj-spec/matrix-prp',id:1261866723},
  head_repository:{full_name:'micor-cjj-spec/matrix-prp',id:1261866723},
  pull_requests:[{number:prNumber,head:{sha},base:{ref:baseRef}}]}
}
const policy=()=>({
  "id": 28050327,
  "name": "protect-collab-integration",
  "target": "branch",
  "source_type": "Repository",
  "source": "micor-cjj-spec/matrix-prp",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "exclude": [],
      "include": [
        "refs/heads/integrate/REQ-20261031-001"
      ]
    }
  },
  "rules": [
    {
      "type": "deletion"
    },
    {
      "type": "non_fast_forward"
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "require_extra_approval_for_unattributed_changes": false,
        "allowed_merge_methods": [
          "merge"
        ]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
        "required_status_checks": [
          {
            "context": "backend-tests",
            "integration_id": 15368
          },
          {
            "context": "web-build",
            "integration_id": 15368
          },
          {
            "context": "mobile-build",
            "integration_id": 15368
          },
          {
            "context": "db-migration-integration",
            "integration_id": 15368
          },
          {
            "context": "video-db-integration",
            "integration_id": 15368
          },
          {
            "context": "impact-report",
            "integration_id": 15368
          },
          {
            "context": "dev-collab-contract",
            "integration_id": 15368
          }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5LNo7jzgGsA5c",
  "created_at": "2026-11-25T05:47:06.929Z",
  "updated_at": "2026-11-25T05:47:07.076Z",
  "bypass_actors": [],
  "current_user_can_bypass": "never"
})
function fakeJobs(route,headRef){
 const id=Number(route.match(/\/runs\/(\d+)\/jobs/)[1]);const run=fakeRun('/'+id,'',headRef,138)
 const jobs=checks.check_runs.filter(c=>c.details_url.includes('/runs/'+id+'/')).map(c=>({name:c.name,id:c.id,run_id:id,run_attempt:1,head_sha:sha,head_branch:headRef,workflow_name:run.name,status:'completed',conclusion:'success',started_at:'2026-10-31T17:01:00Z',completed_at:'2026-10-31T17:59:00Z'}))
 return {total_count:jobs.length,jobs}
}
function fake(path){
 if(path.endsWith('/rulesets/28050327'))return policy()
 if(path.endsWith('/branches/main'))return{name:'main',protected:true,commit:{sha:branchSha}}
 if(path.includes('/jobs?'))return fakeJobs(path,'feat/task-001')
 if(path.endsWith('/pulls/138'))return{number:138,changed_files:1,head:{sha,ref:'feat/task-001',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
 base:{ref:'integrate/'+req,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
 merged:true,merged_at:'2026-10-31T18:00:00Z',merge_commit_sha:merge}
 if(path.includes('/branches/'))return{name:'integrate/'+req,protected:true,commit:{sha:branchSha}}
 if(path.includes('/compare/'))return{status:'ahead',behind_by:0,base_commit:{sha:merge},merge_base_commit:{sha:merge},commits:[]}
 if(path.includes('/pulls/138/files?'))return [{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}]
 if(path.includes('/check-runs'))return checks
 if(path.includes('/actions/runs/'))return fakeRun(path,'integrate/'+req,'feat/task-001',138)
 throw new Error('unexpected request '+path)
}
test('trusted reviewed action may consume exact verified GitHub evidence',()=>{
 const o=trustedReviewContext(state(),{type:'accept',task_id:'T-001',pr_number:138,head_sha:sha},ctx,fake)
 assert.deepEqual(o,{reviewerAuthorized:true,ciVerified:true,mergedIntoIntegration:true})
})
test('outside workflow or foreign actor cannot forge reviewer authorization',()=>{
 for(const bad of [{...ctx,GITHUB_ACTIONS:'false'},{...ctx,GITHUB_ACTOR:'other'},{...ctx,GH_TOKEN:''}]){
  assert.throws(()=>trustedReviewContext(state(),{type:'accept',task_id:'T-001',pr_number:138,head_sha:sha},bad,fake),
    e=>e.code==='UNTRUSTED_REVIEW_CONTEXT')
 }
})
test('wrong submitted SHA rejected before GitHub API lookup',()=>{
 assert.throws(()=>trustedReviewContext(state(),
  {type:'accept',task_id:'T-001',pr_number:138,head_sha:'d'.repeat(40)},
  ctx,()=>{throw new Error('must not fetch') }),e=>e.code==='REVIEW_TASK_MISMATCH')
})
test('failed or unprotected integration evidence does not grant context',()=>{
 assert.throws(()=>trustedReviewContext(state(),{type:'accept',task_id:'T-001',pr_number:138,head_sha:sha},ctx,
   route=>route.includes('/branches/')?{...fake(route),protected:false}:fake(route)),
   e=>e.code==='UNPROTECTED_INTEGRATION_BRANCH')
})


const validDevCloseApi=route=>{
 const integral='d'.repeat(40)
 if(route.endsWith('/rulesets/28050327'))return policy()
 if(route.includes('/jobs?'))return fakeJobs(route,'dev')
 if(route.endsWith('/pulls/139'))return {number:139,
   head:{ref:'dev',sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
   base:{ref:'main',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
   merged:true,merged_at:'2026-11-23T00:00:00Z',merge_commit_sha:merge}
 if(route.endsWith('/branches/main'))return{name:'main',protected:true,commit:{sha:branchSha}}
 if(route.includes('/branches/'))return{
   name:'integrate/'+req,protected:true,commit:{sha:integral}}
 if(route.includes('/compare/')){
   if(route.includes('/compare/'+merge+'...'))
     return{status:'ahead',behind_by:0,base_commit:{sha:merge},
       merge_base_commit:{sha:merge},commits:[]}
   if(route.includes('/compare/'+integral+'...'))
     return{status:'ahead',behind_by:0,base_commit:{sha:integral},
       merge_base_commit:{sha:integral},commits:[]}
   if(route.includes('/compare/'+sha+'...'))
     return{status:'ahead',behind_by:0,base_commit:{sha},
       merge_base_commit:{sha},commits:[]}
 }
 if(route.includes('/check-runs'))return checks
 if(route.includes('/actions/runs/'))return fakeRun(route,'main','dev',139)
 throw new Error('unexpected route '+route)
}
test('owner close proves accepted protected integration history inside merged dev -> main PR',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const proof=trustedReviewContext(s,command,ctx,validDevCloseApi)
 assert.deepEqual(proof,{reviewerAuthorized:true,
   acceptanceApproved:true,integrationReviewVerified:true})
})
test('main protection, integration protection and integration ancestry remain mandatory',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const noMain=route=>route.endsWith('/branches/main')?
   {...validDevCloseApi(route),protected:false}:validDevCloseApi(route)
 assert.throws(()=>trustedReviewContext(s,command,ctx,noMain),
   e=>e.code==='MAIN_NOT_PROTECTED')
 const noIntegration=route=>route.includes('/branches/')&&!route.endsWith('/branches/main')?
   {...validDevCloseApi(route),protected:false}:validDevCloseApi(route)
 assert.throws(()=>trustedReviewContext(s,command,ctx,noIntegration),
   e=>e.code==='INTEGRATION_BRANCH_NOT_PROTECTED')
 const noAncestry=route=>route.includes('/compare/'+'d'.repeat(40)+'...')?
   {...validDevCloseApi(route),behind_by:1}:validDevCloseApi(route)
 assert.throws(()=>trustedReviewContext(s,command,ctx,noAncestry),
   e=>e.code==='INTEGRATION_NOT_IN_DEV_ANCESTRY')
})
test('owner cannot close if any task unfinished even with valid dev -> main evidence',()=>{
 const command={type:'close',pr_number:139,head_sha:sha}
 assert.throws(()=>trustedReviewContext(state(),command,ctx,validDevCloseApi),
   e=>e.code==='INCOMPLETE_REQUIREMENT')
})
test('direct integration -> main cannot be accepted as final release even with green CI',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const direct=route=>route.endsWith('/pulls/139')?
   {...validDevCloseApi(route),head:{...validDevCloseApi(route).head,
     ref:'integrate/'+req}}:validDevCloseApi(route)
 assert.throws(()=>trustedReviewContext(s,command,ctx,direct),
   e=>e.code==='WRONG_MAIN_RELEASE_TARGET')
})

test('trusted close refuses squash-only main merge without dev head ancestry',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const squash=route=>route.includes('/compare/'+sha+'...')?
   {...validDevCloseApi(route),behind_by:1}:validDevCloseApi(route)
 assert.throws(()=>trustedReviewContext(s,command,ctx,squash),
   e=>e.code==='DEV_HEAD_NOT_IN_MAIN_ANCESTRY')
})


test('review entrypoint requires exact workflow-event pair and fresh main SHA',()=>{
 const cmd={type:'accept',task_id:'T-001',pr_number:138,head_sha:sha}
 for(const e of [{...ctx,GITHUB_EVENT_NAME:'pull_request'},{...ctx,GITHUB_WORKFLOW_REF:'other'}, {...ctx,GITHUB_SHA:''}])assert.throws(()=>trustedReviewContext(state(),cmd,e,fake),x=>x.code==='UNTRUSTED_REVIEW_ENTRYPOINT')
 assert.throws(()=>trustedReviewContext(state(),cmd,{...ctx,GITHUB_SHA:'d'.repeat(40)},fake),x=>x.code==='REVIEW_MAIN_REVISION_MISMATCH')
 const issue={...ctx,GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',GITHUB_WORKFLOW_REF:ctx.GITHUB_REPOSITORY+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'}
 assert.equal(trustedReviewContext(state(),cmd,issue,fake).ciVerified,true)
 assert.throws(()=>trustedReviewContext(state(),cmd,{...issue,GITHUB_EVENT_ACTION:'edited'},fake),x=>x.code==='UNTRUSTED_REVIEW_ENTRYPOINT')
 assert.throws(()=>trustedReviewContext(state(),{type:'close',pr_number:139,head_sha:sha},issue,validDevCloseApi),x=>x.code==='UNTRUSTED_REVIEW_ENTRYPOINT')
})
test('generic review fails closed if complete integration policy cannot be seen',()=>{
 const cmd={type:'accept',task_id:'T-001',pr_number:138,head_sha:sha}
 assert.throws(()=>trustedReviewContext(state(),cmd,ctx,route=>{const x=fake(route);if(route.endsWith('/rulesets/28050327'))delete x.bypass_actors;return x}),e=>e.code==='INTEGRATION_POLICY_BYPASS_UNVERIFIED')
})

const squashBase='e'.repeat(40),squashTest='f'.repeat(40),squashTree='1'.repeat(40)
const squashApi=route=>{
 if(route.endsWith('/pulls/139')){
  const pr=validDevCloseApi(route);pr.base.sha=squashBase;pr.base.repo.id=1261866723;pr.head.repo.id=1261866723;return pr
 }
 if(route.includes('/compare/'+sha+'...'))return {status:'diverged',behind_by:1,base_commit:{sha},merge_base_commit:{sha:squashBase},commits:[]}
 if(route.includes('/git/commits/'))return route.endsWith('/'+merge)?
   {sha:merge,tree:{sha:squashTree},parents:[{sha:squashBase}]}:
   {sha:squashTest,tree:{sha:squashTree},parents:[{sha:squashBase},{sha}]}
 if(route.includes('/contents/.github/workflows/'))return {sha:squashTree}
 if(route.includes('/jobs?')){
  const x=fakeJobs(route,'dev')
  for(const j of x.jobs){
   const action=j.workflow_name==='CI'?'v4':'3d3c42e5aac5ba805825da76410c181273ba90b1'
   j.steps=[{name:'Set up job',conclusion:'success'},{name:'Run actions/checkout@'+action,conclusion:'success',started_at:'2026-10-31T17:02:00Z',completed_at:'2026-10-31T17:02:05Z'}]
  }
  return x
 }
 if(route.endsWith('/logs')){
  const id=Number(route.split('/').at(-2)),name=checks.check_runs.find(c=>c.id===id).name
  const action=['impact-report','dev-collab-contract'].includes(name)?'3d3c42e5aac5ba805825da76410c181273ba90b1':'v4'
  const resolved=action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':action
  return [
   "2026-10-31T17:01:59Z Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")",
   '2026-10-31T17:02:00Z ##[group]Run actions/checkout@'+action,
   '2026-10-31T17:02:01Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags origin +'+squashTest+':refs/remotes/pull/139/merge',
   '2026-10-31T17:02:02Z [command]/usr/bin/git checkout --progress --force refs/remotes/pull/139/merge',
   '2026-10-31T17:02:03Z [command]/usr/bin/git log -1 --format=%H',
   '2026-10-31T17:02:04Z '+squashTest,
   '2026-10-31T17:02:06Z ##[group]Run tests'
  ].join('\n')
 }
 if(route.includes('/actions/runs/')){
  const run=validDevCloseApi(route)
  run.pull_requests[0].base.sha=squashBase
  run.pull_requests[0].base.repo={id:1261866723}
  run.pull_requests[0].head.repo={id:1261866723}
  run.pull_requests[0].head.ref='dev'
  return run
 }
 return validDevCloseApi(route)
}
test('trusted close obtains seven real-checkout proofs for a verified squash',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const cmd={type:'close',pr_number:139,head_sha:sha}
 const requested=[]
 const out=trustedReviewContext(s,cmd,ctx,route=>{if(route.endsWith('/logs'))requested.push(route);return squashApi(route)})
 assert.equal(out.integrationReviewVerified,true);assert.equal(new Set(requested).size,7)
})
test('trusted squash refuses missing associations, wrong checkout, missing bypass list or altered squash tree',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const cmd={type:'close',pr_number:139,head_sha:sha}
 for(const [matcher,change,code] of [
  [r=>r.includes('/actions/runs/')&&!r.includes('/jobs?'),x=>({...x,pull_requests:[]}),'WORKFLOW_PR_MISMATCH_backend-tests'],
  [r=>r.endsWith('/logs'),x=>x.replace('refs/remotes/pull/139/merge','refs/remotes/pull/999/merge'),'REVIEW_CHECKOUT_REF_OR_SHA'],
  [r=>r.endsWith('/rulesets/28050327'),x=>{delete x.bypass_actors;return x},'INTEGRATION_POLICY_BYPASS_UNVERIFIED'],
  [r=>r.endsWith('/git/commits/'+merge),x=>({...x,tree:{sha:'2'.repeat(40)}}),'SQUASH_TEST_TREE_MISMATCH'],
 ])assert.throws(()=>trustedReviewContext(s,cmd,ctx,r=>{const x=squashApi(r);return matcher(r)?change(x):x}),e=>e.code===code)
})


const issueEnv={...ctx,GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',
 GITHUB_WORKFLOW_REF:ctx.GITHUB_REPOSITORY+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main',
 GITHUB_RUN_ID:'9001',GITHUB_RUN_ATTEMPT:'1'}
const makeIssueProof=()=>{
 const observedAt=new Date(Date.now()-60000).toISOString(),issueCreatedAt=new Date(Date.now()-30000).toISOString()
 const stateSha='9'.repeat(40),requestId='22222222-2222-4222-8222-222222222222'
 const note=buildOwnerRulesetAttestation(policy(),{requestId,action:'accept',
  requirementId:req,taskId:'T-001',prNumber:138,headSha:sha,stateVersion:1,
  mainSha:branchSha,stateSha,observedAt})
 const cmd={type:'accept',task_id:'T-001',pr_number:138,head_sha:sha,request_id:requestId,requirement_id:req,note}
 const proof={actorId:123868412,sourceIssue:500,issueCreatedAt,stateSha,
  expectedStateSha:stateSha,expectedVersion:1,note}
 const run={id:9001,event:'issues',path:'.github/workflows/prp-collab-issue-ingress.yml',
  status:'in_progress',head_branch:'main',head_sha:branchSha,run_attempt:1,
  created_at:new Date(Date.parse(issueCreatedAt)+1000).toISOString(),
  actor:{login:'micor-cjj-spec',id:123868412},repository:{full_name:'micor-cjj-spec/matrix-prp',id:1261866723}}
 const api=route=>{
  if(route.endsWith('/rulesets/28050327')){const x=policy();delete x.bypass_actors;return x}
  if(route.endsWith('/actions/runs/9001'))return structuredClone(run)
  return fake(route)
 }
 return {cmd,proof,api,run}
}
test('existing authenticated Issue transaction transports exact fresh owner policy and requires state SHA',()=>{
 const {cmd,proof,api}=makeIssueProof()
 const result=trustedReviewContext(state(),cmd,issueEnv,api,proof)
 assert.equal(result.ciVerified,true);assert.equal(result.ownerRulesetAttested,true)
 // A complete runtime list, if visible, must also match the attested policy.
 assert.equal(trustedReviewContext(state(),cmd,issueEnv,r=>r.endsWith('/rulesets/28050327')?policy():api(r),proof).ownerRulesetAttested,true)
 for(const bad of [undefined,{...proof,actorId:999},{...proof,expectedVersion:2},
  {...proof,stateSha:'8'.repeat(40)},{...proof,note:'modified'}]){
  assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,api,bad),e=>e.code==='OWNER_RULESET_ISSUE_CONTEXT_REQUIRED')
 }
 const shifted={...proof,stateSha:'8'.repeat(40),expectedStateSha:'8'.repeat(40)}
 assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,api,shifted),e=>e.code==='OWNER_RULESET_ATTESTATION_BINDING')
})
test('owner Issue proof rejects invalid run identity, stale proof and reruns',()=>{
 const {cmd,proof,api}=makeIssueProof()
 for(const mutate of [x=>x.actor.id=999,x=>x.run_attempt=2,x=>x.head_branch='dev',
  x=>x.head_sha='e'.repeat(40),x=>x.path='.github/workflows/other.yml',x=>x.repository.id=1,
  x=>x.event='workflow_dispatch',x=>x.created_at='2020-01-01T00:00:00Z']){
  assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,r=>{const x=api(r);if(r.endsWith('/actions/runs/9001'))mutate(x);return x},proof),e=>e.code==='OWNER_RULESET_WORKFLOW_IDENTITY')
 }
 assert.throws(()=>trustedReviewContext(state(),cmd,{...issueEnv,GITHUB_RUN_ATTEMPT:'2'},api,proof),e=>e.code==='OWNER_RULESET_WORKFLOW_RUN')
 const old={...proof,issueCreatedAt:new Date(Date.now()-700000).toISOString()}
 assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,api,old),e=>e.code==='OWNER_RULESET_ATTESTATION_EXPIRED')
})
test('manual coordinator cannot substitute owner note for missing bypass list before final recheck is wired',()=>{
 const {cmd,proof,api}=makeIssueProof()
 assert.throws(()=>trustedReviewContext(state(),cmd,ctx,api,proof),e=>e.code==='OWNER_RULESET_ISSUE_CONTEXT_REQUIRED')
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const close={type:'close',pr_number:139,head_sha:sha,note:cmd.note}
 assert.throws(()=>trustedReviewContext(s,close,ctx,r=>{if(r.endsWith('/rulesets/28050327')){const x=policy();delete x.bypass_actors;return x}return validDevCloseApi(r)}),e=>e.code==='OWNER_RULESET_ISSUE_CONTEXT_REQUIRED')
})

test('explicit receipt mode cannot be selected through ordinary accept or manual workflow',()=>{
 const {cmd,proof,api}=makeIssueProof(),marked={...cmd,note:'PRP_PREMERGE_RECEIPT_V1:'+cmd.note}
 assert.throws(()=>trustedReviewContext(state(),marked,issueEnv,api,{...proof,note:marked.note}),/RECEIPT_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,api,{...proof,receiptAccept:true}),/RECEIPT_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),marked,ctx,api,{...proof,receiptAccept:true,note:marked.note}),/RECEIPT_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),{...cmd,type:'capture_receipt'},issueEnv,api,proof),/RECEIPT_EXPLICIT_ISSUE_REQUIRED/)
})

test('historical #271 cannot be selected by manual or ordinary accept or bypass runtime verifier',()=>{
 const {cmd,proof,api}=makeIssueProof(),marked={...cmd,note:'PRP_HISTORICAL_271_V1:'+cmd.note}
 const hp={...proof,historical271:true,note:marked.note}
 assert.throws(()=>trustedReviewContext(state(),marked,ctx,api,hp),/HISTORICAL_271_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),marked,issueEnv,api,{...proof,note:marked.note}),/HISTORICAL_271_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),cmd,issueEnv,api,{...proof,historical271:true}),/HISTORICAL_271_EXPLICIT_ISSUE_REQUIRED/)
 assert.throws(()=>trustedReviewContext(state(),marked,issueEnv,api,hp),/HISTORICAL_271_RUNTIME_REQUIRED/)
 const runtime={verifyHistorical271:()=>({historical271Verified:false})}
 assert.throws(()=>trustedReviewContext(state(),marked,issueEnv,api,hp,undefined,runtime),/HISTORICAL_271_EVIDENCE_REQUIRED/)
})


const h529={
 base:'edd6d76b6c803ea5734f40fc1350ea3b29018562',
 head:'4397169413cd1c43844c7ac21fddc3016e5dfcba',
 merge:'c567761ee555e8d4ec9fa120468a74d8dae97fa8',
 test:'ed2952343acf7c3f151b4380589dcda60ac5fa18',
 tree:'1f9721e95c1d4d3029ae1b8c4c18efbdce551a0a',
 integration:'6c2c3603259829c7d55437f8ed9a2b34f8c165f2',
 ci:'.github/workflows/ci.yml',
 impact:'.github/workflows/feature-impact.yml',
 contract:'.github/workflows/prp-dev-collab-contract.yml'
}
const h529Entries=[
 ['backend-tests',140448213160,45980919751,2,h529.ci,'CI','v4'],
 ['web-build',140448215660,45980919751,2,h529.ci,'CI','v4'],
 ['mobile-build',140448203693,45980919751,2,h529.ci,'CI','v4'],
 ['db-migration-integration',140448233338,45980919751,2,h529.ci,'CI','v4'],
 ['video-db-integration',140448231019,45980919751,2,h529.ci,'CI','v4'],
 ['impact-report',140444287659,45980919689,1,h529.impact,'Feature Impact Report','3d3c42e5aac5ba805825da76410c181273ba90b1'],
 ['dev-collab-contract',140444288158,45980919800,1,h529.contract,'PRP Dev Collaboration Contract','3d3c42e5aac5ba805825da76410c181273ba90b1']
]
function h529CloseFixture(){
 const repoName='micor-cjj-spec/matrix-prp'
 const pr={number:529,state:'closed',merged:true,draft:false,merge_commit_sha:h529.merge,merged_at:'2026-11-27T10:48:31Z',changed_files:7,
  base:{ref:'main',sha:h529.base,repo:{full_name:repoName,id:1261866723}},
  head:{ref:'dev',sha:h529.head,repo:{full_name:repoName,id:1261866723}}}
 const main={name:'main',protected:true,commit:{sha:branchSha}}
 const integrationBranch={name:'integrate/'+req,protected:true,commit:{sha:h529.integration}}
 const files=[
  ['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md','added'],
  ['app/docs/dev-collab/OPERATIONS.md','modified'],
  ['app/scripts/dev-collab/core.mjs','modified'],
  ['app/scripts/dev-collab/core.test.mjs','modified'],
  ['app/scripts/dev-collab/integration-ci-boundary.test.mjs','modified'],
  ['app/scripts/dev-collab/recovery.mjs','modified'],
  ['app/scripts/dev-collab/recovery.test.mjs','modified']
 ].map(([filename,status])=>({filename,status}))
 const blobMap={
  [h529.ci]:'2e8ded58e20cf540c033365ed266d0e2045309b6',
  [h529.impact]:'5a64a9e728f4bb6dd0fc91bb0393b2cca74ae302',
  [h529.contract]:'c1373ee788d3469aea37624328f4e53e66a68f9c'
 }
 const runs={
  45980919751:{id:45980919751,name:'CI',path:h529.ci,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:2,created_at:'2026-11-27T09:58:00Z',repository:{full_name:repoName,id:1261866723},head_repository:{full_name:repoName,id:1261866723},pull_requests:[]},
  45980919689:{id:45980919689,name:'Feature Impact Report',path:h529.impact,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:1,created_at:'2026-11-27T09:58:00Z',repository:{full_name:repoName,id:1261866723},head_repository:{full_name:repoName,id:1261866723},pull_requests:[]},
  45980919800:{id:45980919800,name:'PRP Dev Collaboration Contract',path:h529.contract,event:'pull_request',status:'completed',conclusion:'success',head_sha:h529.head,head_branch:'dev',run_attempt:1,created_at:'2026-11-27T09:58:00Z',repository:{full_name:repoName,id:1261866723},head_repository:{full_name:repoName,id:1261866723},pull_requests:[]}
 }
 const jobs={},logs={},checkRuns=[]
 for(const [name,id,run,attempt,path,workflow,action] of h529Entries){
  const start='2026-11-27T10:00:00Z',end='2026-11-27T10:00:05Z'
  const steps=[{name:'Set up job',conclusion:'success'}]
  if(name==='db-migration-integration'||name==='video-db-integration')steps.push({name:'Initialize containers',conclusion:'success'})
  steps.push({name:'Run actions/checkout@'+action,conclusion:'success',started_at:start,completed_at:end})
  const job={name,id,run_id:run,run_attempt:attempt,head_sha:h529.head,head_branch:'dev',workflow_name:workflow,status:'completed',conclusion:'success',
   started_at:'2026-11-27T09:59:00Z',completed_at:'2026-11-27T10:01:00Z',steps}
  if(!jobs[run])jobs[run]={total_count:0,jobs:[]}
  jobs[run].jobs.push(job);jobs[run].total_count++
  const fetchLine=name==='impact-report'
   ?'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules origin +refs/heads/*:refs/remotes/origin/* +refs/tags/*:refs/tags/* +'+h529.test+':refs/remotes/pull/529/merge'
   :name==='dev-collab-contract'
    ?'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=2 origin +'+h529.test+':refs/remotes/pull/529/merge'
    :'[command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +'+h529.test+':refs/remotes/pull/529/merge'
  const resolved=action==='v4'?'11d5960a326750d5838078e36cf38b85af677262':action
  logs[id]=[
   "2026-11-27T09:59:59Z Download action repository 'actions/checkout@"+action+"' (SHA:"+resolved+")",
   "2026-11-27T10:00:00Z ##[group]Run actions/checkout@"+action,
   "2026-11-27T10:00:01Z "+fetchLine,
   "2026-11-27T10:00:02Z [command]/usr/bin/git checkout --progress --force refs/remotes/pull/529/merge",
   "2026-11-27T10:00:03Z [command]/usr/bin/git log -1 --format=%H",
   "2026-11-27T10:00:04Z "+h529.test,
   "2026-11-27T10:00:05Z ##[group]Run next step"
  ].join('\n')
  checkRuns.push({name,id,head_sha:h529.head,status:'completed',conclusion:'success',app:{slug:'github-actions',id:15368},
   details_url:'https://github.com/'+repoName+'/actions/runs/'+run+'/job/'+id,
   started_at:'2026-11-27T09:59:00Z',completed_at:'2026-11-27T10:01:00Z'})
 }
 const checks={total_count:checkRuns.length,check_runs:checkRuns}
 const testCommit={sha:h529.test,tree:{sha:h529.tree},parents:[{sha:h529.base},{sha:h529.head}]}
 const mergeCommit={sha:h529.merge,tree:{sha:h529.tree},parents:[{sha:h529.base}]}
 const timeline=[{event:'merged',commit_id:h529.merge,created_at:'2026-11-27T10:48:31Z'}]
 const api=route=>{
  if(route.endsWith('/rulesets/28050327'))return policy()
  if(route.endsWith('/pulls/529'))return structuredClone(pr)
  if(route.endsWith('/branches/main'))return structuredClone(main)
  if(route.endsWith('/branches/'+encodeURIComponent('integrate/'+req)))return structuredClone(integrationBranch)
  if(route.includes('/compare/'+h529.merge+'...'))return{status:'ahead',behind_by:0,base_commit:{sha:h529.merge},merge_base_commit:{sha:h529.merge},commits:[]}
  if(route.includes('/compare/'+h529.integration+'...'))return{status:'ahead',behind_by:0,base_commit:{sha:h529.integration},merge_base_commit:{sha:h529.integration},commits:[]}
  if(route.includes('/compare/'+h529.head+'...'))return{status:'diverged',behind_by:1,base_commit:{sha:h529.head},merge_base_commit:{sha:h529.base},commits:[{sha:h529.merge}]}
  if(route.includes('/commits/'+h529.head+'/check-runs'))return checks
  if(route.endsWith('/issues/529/timeline?per_page=100&page=1'))return timeline
  if(route.endsWith('/issues/529/timeline?per_page=100&page=2'))return []
  if(route.endsWith('/pulls/529/files?per_page=100'))return files
  if(route.endsWith('/git/commits/'+h529.test))return testCommit
  if(route.endsWith('/git/commits/'+h529.merge))return mergeCommit
  if(route.includes('/actions/runs/')&&route.includes('/jobs?'))return jobs[Number(route.match(/\/runs\/(\d+)\/jobs/)[1])]
  if(route.includes('/actions/runs/'))return runs[Number(route.split('/').at(-1))]
  if(route.includes('/actions/jobs/'))return logs[Number(route.match(/\/jobs\/(\d+)\/logs/)[1])]
  if(route.includes('/contents/')){
   const [path,ref]=route.split('/contents/')[1].split('?ref=')
   return {sha:[h529.base,h529.test,h529.merge].includes(ref)?blobMap[path]:undefined}
  }
  throw Error('unexpected route '+route)
 }
 const s=state()
 s.version=49
 s.tasks=Array.from({length:9},(_,i)=>({task_id:'T-'+String(i+1).padStart(3,'0'),issue_number:133+i,
  title:'Task '+(i+1),status:'DONE',depends_on:[],allowed_paths:['app/scripts/dev-collab/'],claim:null}))
 const command={type:'close',pr_number:529,head_sha:h529.head,note:HISTORICAL_529_PREFIX}
 return {snapshot:s,command,api}
}
test('owner manual close uses only the exact historical #529 proof and existing squash release gate',()=>{
 const {snapshot,command,api}=h529CloseFixture()
 const result=trustedReviewContext(snapshot,command,ctx,api)
 assert.deepEqual(result,{reviewerAuthorized:true,acceptanceApproved:true,integrationReviewVerified:true,historical529Verified:true})
})
test('historical #529 selector is manual-close only and cannot widen generic PR association rules',()=>{
 const {snapshot,command,api}=h529CloseFixture()
 assert.throws(()=>trustedReviewContext(snapshot,{...command,note:undefined},ctx,api),
  e=>e.code==='WORKFLOW_PR_MISMATCH_backend-tests')
 assert.throws(()=>trustedReviewContext(snapshot,{...command,type:'accept'},ctx,api),
  e=>e.code==='HISTORICAL_529_EXPLICIT_MANUAL_CLOSE_REQUIRED')
 const issue={...ctx,GITHUB_EVENT_NAME:'issues',GITHUB_EVENT_ACTION:'opened',
  GITHUB_WORKFLOW_REF:ctx.GITHUB_REPOSITORY+'/.github/workflows/prp-collab-issue-ingress.yml@refs/heads/main'}
 assert.throws(()=>trustedReviewContext(snapshot,command,issue,api),
  e=>e.code==='UNTRUSTED_REVIEW_ENTRYPOINT')
 assert.throws(()=>trustedReviewContext(snapshot,{...command,pr_number:528},ctx,api),
  e=>e.message==='HISTORICAL_529_BINDING')
})
test('historical #529 close rejects altered run association and test ancestry',()=>{
 const {snapshot,command,api}=h529CloseFixture()
 assert.throws(()=>trustedReviewContext(snapshot,command,ctx,route=>{
  const x=api(route)
  if(route.endsWith('/actions/runs/45980919751'))x.pull_requests=[{number:528}]
  return x
 }),e=>e.message==='HISTORICAL_529_RUN_MISMATCH')
 assert.throws(()=>trustedReviewContext(snapshot,command,ctx,route=>{
  const x=api(route)
  if(route.endsWith('/git/commits/'+h529.test))x.parents[1].sha='f'.repeat(40)
  return x
 }),e=>e.message==='HISTORICAL_529_COMMIT_MISMATCH')
})
