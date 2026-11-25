import test from 'node:test'
import assert from 'node:assert/strict'
import { trustedReviewContext } from './review-context.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'
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

const ownerRun=(env,createdAt)=>({id:Number(env.GITHUB_RUN_ID),event:'workflow_dispatch',
 path:'.github/workflows/prp-collab-coordinator.yml',status:'in_progress',head_branch:'main',
 head_sha:branchSha,run_attempt:1,created_at:createdAt,
 actor:{login:'micor-cjj-spec',id:123868412},
 repository:{full_name:'micor-cjj-spec/matrix-prp',id:1261866723}})
test('trusted accept accepts redacted Ruleset only with a fresh owner-run attestation',()=>{
 const observedAt=new Date(Date.now()-60000).toISOString()
 const runEnv={...ctx,GITHUB_RUN_ID:'9001',GITHUB_RUN_ATTEMPT:'1'}
 const note=buildOwnerRulesetAttestation(policy(),{requestId:'22222222-2222-4222-8222-222222222222',
  action:'accept',requirementId:req,taskId:'T-001',prNumber:138,headSha:sha,
  stateVersion:1,mainSha:branchSha,observedAt})
 const cmd={type:'accept',task_id:'T-001',pr_number:138,head_sha:sha,
  request_id:'22222222-2222-4222-8222-222222222222',requirement_id:req,note}
 const api=route=>{
  if(route.endsWith('/rulesets/28050327')){const x=policy();delete x.bypass_actors;return x}
  if(route.endsWith('/actions/runs/9001'))return ownerRun(runEnv,new Date(Date.parse(observedAt)+30000).toISOString())
  return fake(route)
 }
 const result=trustedReviewContext(state(),cmd,runEnv,api)
 assert.equal(result.ciVerified,true)
})
test('owner attestation rejects wrong workflow actor, rerun, branch or main SHA',()=>{
 const observedAt=new Date(Date.now()-60000).toISOString()
 const runEnv={...ctx,GITHUB_RUN_ID:'9002',GITHUB_RUN_ATTEMPT:'1'}
 const note=buildOwnerRulesetAttestation(policy(),{requestId:'33333333-3333-4333-8333-333333333333',
  action:'accept',requirementId:req,taskId:'T-001',prNumber:138,headSha:sha,
  stateVersion:1,mainSha:branchSha,observedAt})
 const cmd={type:'accept',task_id:'T-001',pr_number:138,head_sha:sha,
  request_id:'33333333-3333-4333-8333-333333333333',requirement_id:req,note}
 for(const mutate of [
  x=>x.actor.id=999,x=>x.run_attempt=2,x=>x.head_branch='dev',x=>x.head_sha='e'.repeat(40),
  x=>x.path='.github/workflows/other.yml',x=>x.repository.id=1
 ]){
  assert.throws(()=>trustedReviewContext(state(),cmd,runEnv,route=>{
   if(route.endsWith('/rulesets/28050327')){const x=policy();delete x.bypass_actors;return x}
   if(route.endsWith('/actions/runs/9002')){const x=ownerRun(runEnv,new Date(Date.parse(observedAt)+30000).toISOString());mutate(x);return x}
   return fake(route)
  }),e=>e.code==='OWNER_RULESET_WORKFLOW_IDENTITY')
 }
 assert.throws(()=>trustedReviewContext(state(),cmd,{...runEnv,GITHUB_RUN_ATTEMPT:'2'},route=>{
  if(route.endsWith('/rulesets/28050327')){const x=policy();delete x.bypass_actors;return x}
  throw new Error('workflow run must not be queried on rerun')
 }),e=>e.code==='OWNER_RULESET_WORKFLOW_RUN')
})
