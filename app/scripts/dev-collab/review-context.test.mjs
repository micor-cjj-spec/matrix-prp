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
 started_at:'2026-10-31T18:00:00Z',app:{slug:'github-actions'}
}))}
function fake(path){
 if(path.endsWith('/pulls/138'))return{number:138,head:{sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
 base:{ref:'integrate/'+req,repo:{full_name:'micor-cjj-spec/matrix-prp'}},
 merged:true,merged_at:'2026-10-31T18:00:00Z',merge_commit_sha:merge}
 if(path.includes('/branches/'))return{name:'integrate/'+req,protected:true,commit:{sha:branchSha}}
 if(path.includes('/compare/'))return{status:'ahead',behind_by:0,base_commit:{sha:merge},merge_base_commit:{sha:merge},commits:[]}
 if(path.includes('/check-runs'))return checks
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
