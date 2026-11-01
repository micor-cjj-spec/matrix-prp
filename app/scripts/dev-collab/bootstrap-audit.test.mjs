import test from 'node:test'
import assert from 'node:assert/strict'
import { auditBootstrap } from './bootstrap-audit.mjs'
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
