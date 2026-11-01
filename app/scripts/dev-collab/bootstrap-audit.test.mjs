import test from 'node:test'
import assert from 'node:assert/strict'
import { auditBootstrap, verifyScopeMigrationProposal, SCOPE_MIGRATION_FILES } from './bootstrap-audit.mjs'
const state=()=>({
  schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
  title:'Multi-conversation MVP',status:'ACTIVE',version:0,processed_requests:[],
  tasks:[
    {task_id:'T-001',issue_number:133,title:'Core',status:'READY',
      allowed_paths:['app/scripts/dev-collab/core.mjs'],depends_on:[],claim:null},
    {task_id:'T-002',issue_number:134,title:'Templates',status:'READY',
      allowed_paths:['.github/ISSUE_TEMPLATE/'],depends_on:[],claim:null},
    {task_id:'T-003',issue_number:135,title:'Coordinator',status:'READY',
      allowed_paths:['app/scripts/dev-collab/coordinator-cli.mjs'],depends_on:['T-001'],claim:null}
  ]
})
const pr=()=>({number:138,draft:true,merged:false,changed_files:3,base:{ref:'main'}})
const files=()=>[
  {filename:'app/scripts/dev-collab/core.mjs'},
  {filename:'.github/ISSUE_TEMPLATE/task.yml'},
  {filename:'app/scripts/dev-collab/review-gate.mjs'}
]
test('read-only reconciliation detects out-of-scope files and dependency readiness',()=>{
  const result=auditBootstrap(state(),pr(),files())
  assert.deepEqual(result.ready_task_ids,['T-001','T-002'])
  assert.equal(result.pr_base,'main')
  assert.deepEqual(result.unassigned_files,['app/scripts/dev-collab/review-gate.mjs'])
  assert.equal(result.task_acceptance_verified,false)
  assert.equal(result.claim_count,0)
  assert.equal(result.assigned_files_by_task['T-003'].length,0)
})
test('a main-targeted bootstrap PR cannot masquerade as an accepted task PR',()=>{
  const r=pr();r.merged=true
  const result=auditBootstrap(state(),r,files())
  assert.equal(result.task_acceptance_verified,false)
  assert.ok(result.warnings.includes('BOOTSTRAP_PR_NOT_TARGETING_INTEGRATION'))
})
test('truncated or duplicated GitHub PR file evidence is rejected',()=>{
  const p=pr();p.changed_files=4
  assert.throws(()=>auditBootstrap(state(),p,files()),/INCOMPLETE_BOOTSTRAP_PR_FILES/)
  const dup=files();dup[2].filename=dup[0].filename
  assert.throws(()=>auditBootstrap(state(),pr(),dup),/DUPLICATE_BOOTSTRAP_PR_FILE/)
})
test('scope overlaps are visible rather than assigned to an arbitrary worker',()=>{
  const s=state();s.tasks[2].allowed_paths=['app/scripts/dev-collab/'];s.tasks[2].depends_on=[]
  const report=auditBootstrap(s,pr(),files())
  assert.deepEqual(report.overlap_files,['app/scripts/dev-collab/core.mjs'])
  assert.equal(report.task_acceptance_verified,false)
})

test('offline scope audit never certifies actual task acceptance, even when PR shape looks valid',()=>{
  const p=pr();p.base.ref='integrate/REQ-20261031-001';p.merged=true
  const s=state();s.tasks[2].allowed_paths=['app/scripts/dev-collab/review-gate.mjs'];
  const report=auditBootstrap(s,p,files())
  assert.equal(report.matches_integration_pr_shape,true)
  assert.equal(report.task_acceptance_verified,false)
})

const baselineMigration=()=>({
 schema_version:1,requirement_id:'REQ-20261031-001',issue_number:132,
 title:'多 GPT 会话共享开发任务 MVP',status:'ACTIVE',version:0,
 updated_at:'2026-10-31T16:05:00Z',processed_requests:[],
 tasks:[
 {task_id:'T-001',issue_number:133,title:'Core',status:'READY',depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null},
 {task_id:'T-002',issue_number:134,title:'Templates',status:'READY',depends_on:[],allowed_paths:['.github/ISSUE_TEMPLATE/'],claim:null},
 {task_id:'T-003',issue_number:135,title:'Coordinator',status:'READY',depends_on:['T-001'],allowed_paths:['app/scripts/dev-collab/coordinator-cli.mjs'],claim:null},
 {task_id:'T-004',issue_number:136,title:'Docs',status:'READY',depends_on:['T-001','T-003'],allowed_paths:['app/docs/dev-collab/'],claim:null},
 {task_id:'T-005',issue_number:137,title:'Integration',status:'READY',depends_on:['T-001','T-002','T-003','T-004'],allowed_paths:[],claim:null}
 ]
})
const proposedMigration=()=> {
 const x=baselineMigration()
 x.version=1;x.updated_at='2026-11-01T01:42:57.795Z'
 x.tasks[4].allowed_paths=['app/docs/dev-collab/INTEGRATION-ACCEPTANCE.md']
 x.tasks[4].depends_on.push('T-006','T-007','T-008','T-009')
 for(const [tid,issue,deps] of [
  ['T-006',141,['T-003']],['T-007',142,['T-003']],
  ['T-008',143,['T-003','T-007','T-009']],['T-009',146,['T-003','T-007']]
 ]){
  x.tasks.push({task_id:tid,issue_number:issue,title:tid,status:'READY',
   depends_on:deps,allowed_paths:[...SCOPE_MIGRATION_FILES[tid]],claim:null})
 }
 return x
}
const assertMigrationFails=(before,after,code)=>assert.throws(
 ()=>verifyScopeMigrationProposal(before,after),e=>e.message==='SCOPE_MIGRATION_'+code)
test('V0 to V1 scope proposal is structurally safe but cannot authorize application',()=>{
 const result=verifyScopeMigrationProposal(baselineMigration(),proposedMigration())
 assert.equal(result.structurally_valid,true)
 assert.equal(result.ready_for_direct_merge,false)
 assert.deepEqual(result.new_task_ids,['T-006','T-007','T-008','T-009'])
})
test('state migration cannot retroactively claim or mark a historical task DONE',()=>{
 const s=proposedMigration();s.tasks[0].status='DONE'
 assertMigrationFails(baselineMigration(),s,'HISTORIC_TASK_MODIFIED')
 const y=proposedMigration();y.tasks[5].status='DONE'
 assertMigrationFails(baselineMigration(),y,'UNAUTHORIZED_NEW_TASK_SCOPE')
})
test('scope migration refuses broader write paths or CI workflow bypass',()=>{
 const s=proposedMigration();s.tasks[5].allowed_paths=['app/scripts/dev-collab/']
 assertMigrationFails(baselineMigration(),s,'UNAUTHORIZED_NEW_TASK_SCOPE')
 const t=proposedMigration();t.tasks[5].allowed_paths=['.github/workflows/ci.yml',...SCOPE_MIGRATION_FILES['T-006']]
 assertMigrationFails(baselineMigration(),t,'UNAUTHORIZED_NEW_TASK_SCOPE')
})
test('existing task review artifact must be defined and all new task dependencies held',()=>{
 const s=proposedMigration();s.tasks[4].allowed_paths=[]
 assertMigrationFails(baselineMigration(),s,'T005_SCOPE_OR_DEPENDENCIES')
 const t=proposedMigration();t.tasks[7].depends_on=[]
 assertMigrationFails(baselineMigration(),t,'UNAUTHORIZED_NEW_TASK_SCOPE')
})
test('migration must be versioned with unchanged request history',()=>{
 const s=proposedMigration();s.version=0
 assertMigrationFails(baselineMigration(),s,'UNEXPECTED_STATE_CHANGE')
 const t=proposedMigration();t.processed_requests=[{request_id:'bad'}]
 assert.throws(()=>verifyScopeMigrationProposal(baselineMigration(),t))
})

test('recovery task T-009 remains in exact narrow scope and blocks final acceptance',()=>{
 const baseline=baselineMigration()
 const proposed=proposedMigration()
 assert.equal(verifyScopeMigrationProposal(baseline,proposed).new_task_ids.length,4)
 const missing=proposedMigration();missing.tasks.pop()
 assert.throws(()=>verifyScopeMigrationProposal(baseline,missing),e=>e.code==='UNKNOWN_DEPENDENCY')
 const changed=proposedMigration();changed.tasks[8].allowed_paths=['app/scripts/dev-collab/']
 assertMigrationFails(baseline,changed,'UNAUTHORIZED_NEW_TASK_SCOPE')
 const deps=proposedMigration();deps.tasks[4].depends_on.pop()
 assertMigrationFails(baseline,deps,'T005_SCOPE_OR_DEPENDENCIES')
 const tests=proposedMigration();tests.tasks[7].depends_on.pop()
 assertMigrationFails(baseline,tests,'UNAUTHORIZED_NEW_TASK_SCOPE')
})
