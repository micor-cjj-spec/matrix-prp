import test from 'node:test'
import assert from 'node:assert/strict'
import { trustedReviewContext } from './review-context.mjs'
import { REQUIRED_CHECKS } from './review-gate.mjs'
const req='REQ-20261031-001',sha='a'.repeat(40),merge='b'.repeat(40),branchSha='c'.repeat(40)
const ctx={GITHUB_ACTIONS:'true',GITHUB_REF:'refs/heads/main',
 GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_ACTOR:'micor-cjj-spec',
 GITHUB_REPOSITORY_OWNER:'micor-cjj-spec',GH_TOKEN:'synthetic-test-token'}
const state=()=>({schema_version:1,requirement_id:req,issue_number:132,title:'MVP',
 version:1,status:'ACTIVE',processed_requests:[],
 tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'IN_REVIEW',depends_on:[],
 allowed_paths:['app/scripts/dev-collab/'],claim:{claim_id:'11111111-1111-4111-8111-111111111111',actor:'micor-cjj-spec',worker_id:'chat-A'},
 pr_number:138,head_sha:sha}]})
const checks={total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
 name,id:i+1,head_sha:sha,status:'completed',conclusion:'success',
 details_url:'https://github.com/micor-cjj-spec/matrix-prp/actions/runs/'+(name==='impact-report'?102:name==='dev-collab-contract'?103:101)+'/job/'+(i+1),
 started_at:'2026-10-31T18:00:00Z',app:{slug:'github-actions'}
}))}
const fakeRun = (route,baseRef,headRef,prNumber)=>{
 const id=Number(route.split('/').pop())
 const names={101:['CI','.github/workflows/ci.yml'],
   102:['Feature Impact Report','.github/workflows/feature-impact.yml'],
   103:['PRP Dev Collaboration Contract','.github/workflows/prp-dev-collab-contract.yml']}
 const [name,path]=names[id]||[]
 return {name,path,event:'pull_request',status:'completed',conclusion:'success',head_sha:sha,
  head_branch:headRef,repository:{full_name:'micor-cjj-spec/matrix-prp'},
  head_repository:{full_name:'micor-cjj-spec/matrix-prp'},
  pull_requests:[{number:prNumber,head:{sha},base:{ref:baseRef}}]}
}
function fake(path){
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

test('owner can close only with a separately merged and protected main integration PR',()=>{
 const s=state();s.tasks[0].status='DONE';s.tasks[0].claim=null
 const command={type:'close',pr_number:139,head_sha:sha}
 const valid=route=>{
   if(route.endsWith('/pulls/139'))return {number:139,
     head:{ref:'integrate/'+req,sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
     base:{ref:'main',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
     merged:true,merged_at:'2026-10-31T19:00:00Z',merge_commit_sha:merge}
   if(route.endsWith('/branches/main'))return{name:'main',protected:true,commit:{sha:branchSha}}
   if(route.includes('/compare/'))return{status:'ahead',behind_by:0,base_commit:{sha:merge},
     merge_base_commit:{sha:merge},commits:[]}
   if(route.includes('/check-runs'))return checks
   if(route.includes('/actions/runs/'))return fakeRun(route,'main','integrate/'+req,139)
   throw new Error('unexpected route '+route)
 }
 const proof=trustedReviewContext(s,command,ctx,valid)
 assert.deepEqual(proof,{reviewerAuthorized:true,acceptanceApproved:true,integrationReviewVerified:true})
 assert.throws(()=>trustedReviewContext(s,command,ctx,route=>
   route.endsWith('/branches/main')?{...valid(route),protected:false}:valid(route)),
   e=>e.code==='MAIN_NOT_PROTECTED')
})
test('cannot close a requirement with unfinished tasks even if final PR is merged',()=>{
 const s=state()
 const command={type:'close',pr_number:139,head_sha:sha}
 const fakeApproval=route=>{
   if(route.endsWith('/pulls/139'))return{number:139,
     head:{ref:'integrate/'+req,sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
     base:{ref:'main',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
     merged:true,merged_at:'2026-10-31T19:00:00Z',merge_commit_sha:merge}
   if(route.endsWith('/branches/main'))return{name:'main',protected:true,commit:{sha:branchSha}}
   if(route.includes('/compare/'))return{status:'identical',behind_by:0,
     base_commit:{sha:merge},merge_base_commit:{sha:merge}}
   if(route.includes('/check-runs'))return checks
   if(route.includes('/actions/runs/'))return fakeRun(route,'main','integrate/'+req,139)
   throw new Error('unexpected route '+route)
 }
 assert.throws(()=>trustedReviewContext(s,command,ctx,fakeApproval),e=>e.code==='INCOMPLETE_REQUIREMENT')
})
