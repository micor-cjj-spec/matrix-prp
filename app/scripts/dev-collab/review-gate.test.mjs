import test from 'node:test'
import assert from 'node:assert/strict'
import { verifyTaskEvidence, verifyRequirementClose, REQUIRED_CHECKS } from './review-gate.mjs'
const sha='a'.repeat(40),merge='b'.repeat(40),integration='c'.repeat(40)
const make=()=>({schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
  status:'ACTIVE',version:3,title:'MVP',processed_requests:[],
  tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'IN_REVIEW',
    claim:{claim_id:'11111111-1111-4111-8111-111111111111',worker_id:'chat-A',actor:'micor-cjj-spec'},
    depends_on:[],allowed_paths:['app/scripts/dev-collab/'],pr_number:138,head_sha:sha}]})
const pack=()=>({
  pr:{number:138,changed_files:1,merged:true,merged_at:'2026-10-31T18:00:00Z',merge_commit_sha:merge,
    base:{ref:'integrate/REQ-20261031-001',repo:{full_name:'micor-cjj-spec/matrix-prp'}},
    head:{sha,repo:{full_name:'micor-cjj-spec/matrix-prp'}}},
  branch:{name:'integrate/REQ-20261031-001',protected:true,commit:{sha:integration}},
  comparison:{status:'ahead',behind_by:0,base_commit:{sha:merge},merge_base_commit:{sha:merge},commits:[]},
  files:[{filename:'app/scripts/dev-collab/core.mjs',status:'modified'}],
  checks:{total_count:REQUIRED_CHECKS.length,check_runs:REQUIRED_CHECKS.map((name,i)=>({
    name,id:i+1,head_sha:sha,status:'completed',conclusion:'success',
    started_at:'2026-10-31T18:00:00Z',app:{slug:'github-actions'}
  }))}
})
const refuses=(fn,code)=>assert.throws(fn,e=>e.code===code)
test('acceptance verification binds PR, merged integration and 7 exact GitHub checks',()=>{
  const r=verifyTaskEvidence(make(),'T-001',pack())
  assert.equal(r.verified,true)
  assert.equal(r.checks,7)
  assert.equal(r.integration_sha,integration)
})
test('draft or unmerged PR cannot complete a task',()=>{
  const e=pack();e.pr.merged=false
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'PR_NOT_MERGED')
})
test('candidate targets a distinct integration branch, never unreviewed main',()=>{
  const e=pack();e.pr.base.ref='main'
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'WRONG_INTEGRATION_BASE')
})
test('head SHA must match the originally submitted task artifact',()=>{
  const e=pack();e.pr.head.sha='d'.repeat(40)
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'WRONG_PR_OR_HEAD')
})
test('integration branch must be protected',()=>{
  const e=pack();e.branch.protected=false
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'UNPROTECTED_INTEGRATION_BRANCH')
})
test('proof must establish merged commit is still ancestor of integration head',()=>{
  const e=pack();e.comparison.behind_by=1
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'MERGE_NOT_ON_BASE')
})
test('checks must be complete, latest and from verified GitHub Actions app',()=>{
  const e=pack();e.checks.check_runs.pop()
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'INCOMPLETE_CHECK_PAGINATION')
  const f=pack();f.checks.check_runs[0].app.slug='other-app'
  refuses(()=>verifyTaskEvidence(make(),'T-001',f),'CHECK_MISSING_backend-tests')
  const g=pack();g.checks.check_runs[0].conclusion='failure'
  refuses(()=>verifyTaskEvidence(make(),'T-001',g),'CHECK_NOT_GREEN_backend-tests')
})
test('newer failing check defeats earlier green result',()=>{
  const e=pack();e.checks.check_runs.push({...e.checks.check_runs[0],
    started_at:'2026-10-31T19:00:00Z',conclusion:'failure',id:99})
  e.checks.total_count++
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'CHECK_NOT_GREEN_backend-tests')
})
test('foreign GitHub PR repository is refused',()=>{
  const e=pack();e.pr.head.repo.full_name='someone/fork'
  refuses(()=>verifyTaskEvidence(make(),'T-001',e),'FOREIGN_HEAD_REPOSITORY')
})
test('a requirement cannot close until every task is done and owner signs off',()=>{
  const s=make()
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true}), 'INCOMPLETE_REQUIREMENT')
  s.tasks[0].status='DONE';s.tasks[0].claim=null
  refuses(()=>verifyRequirementClose(s,{}),'OWNER_APPROVAL_REQUIRED')
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true}),'EXPLICIT_ACCEPTANCE_REQUIRED')
  refuses(()=>verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true}),'INTEGRATION_REVIEW_REQUIRED')
  assert.equal(verifyRequirementClose(s,{actorIsRepositoryOwner:true,explicitAcceptance:true,integrationReviewVerified:true}).ready_to_close,true)
})

test('wrong file scope or stolen rename cannot pass task acceptance',()=>{
  const a=pack();a.files=[{filename:'app/web/src/App.vue',status:'modified'}]
  refuses(()=>verifyTaskEvidence(make(),'T-001',a),'TASK_FILE_OUTSIDE_SCOPE')
  const b=pack();b.files=[{filename:'app/scripts/dev-collab/core.mjs',status:'renamed',previous_filename:'app/backend/pom.xml'}]
  refuses(()=>verifyTaskEvidence(make(),'T-001',b),'RENAME_SOURCE_OUTSIDE_SCOPE')
})
test('CI workflow modification is never authorized by ordinary task acceptance',()=>{
  const s=make();s.tasks[0].allowed_paths=['.github/workflows/']
  const a=pack();a.files=[{filename:'.github/workflows/ci.yml',status:'modified'}]
  refuses(()=>verifyTaskEvidence(s,'T-001',a),'CRITICAL_WORKFLOW_CHANGE_NOT_ALLOWED')
})
test('incomplete or paginated PR file list fails closed',()=>{
  const a=pack();a.pr.changed_files=2
  refuses(()=>verifyTaskEvidence(make(),'T-001',a),'INCOMPLETE_PR_FILE_LIST')
})
