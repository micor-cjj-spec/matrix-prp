import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync,mkdirSync,writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { spawnSync } from 'node:child_process'
import { listUnfinishedRequirements,recoveryBrief,loadRequirementDirectory } from './recovery.mjs'
const sha='a'.repeat(40)
const state=(id='REQ-20261031-001')=>({
 schema_version:1,requirement_id:id,title:'Task registry',issue_number:132,
 status:'ACTIVE',version:12,processed_requests:[],updated_at:'2026-11-01T02:00:00Z',
 tasks:[
 {task_id:'T-001',title:'Completed',issue_number:133,status:'DONE',
  depends_on:[],allowed_paths:['app/scripts/dev-collab/core.mjs'],claim:null},
 {task_id:'T-002',title:'Recovery needed',issue_number:134,status:'IN_PROGRESS',
  depends_on:['T-001'],allowed_paths:['app/scripts/dev-collab/recovery.mjs'],
  claim:{claim_id:'11111111-1111-4111-8111-111111111111',actor:'micor-cjj-spec',
  worker_id:'chat-A',generation:1},
  checkpoint:{summary:'Implementation pushed',next_step:'Inspect CI logs',
   branch:'feature/recover',head_sha:sha,recorded_at:'2026-11-01T01:50:00Z',
   worker_id:'chat-A',tests:'CI run pending'}},
 {task_id:'T-003',title:'Waiting',issue_number:135,status:'READY',
  depends_on:['T-002'],allowed_paths:['app/docs/dev-collab/'],claim:null}
 ]
})
test('read-only all-requirement index finds open tasks without old chat ID',()=>{
 const a=state(),b=state('REQ-20261031-002')
 b.tasks.splice(1); b.tasks[0].status='READY'
 const result=listUnfinishedRequirements([b,a])
 assert.equal(result.length,2)
 assert.deepEqual(result.map(x=>x.requirement_id),['REQ-20261031-001','REQ-20261031-002'])
 assert.deepEqual(result[0].tasks.map(t=>t.status),['IN_PROGRESS','WAITING'])
 assert.equal(result[0].tasks[0].checkpoint_head_sha,sha)
 assert.equal(JSON.stringify(result).includes('11111111-1111'),false)
 assert.equal(JSON.stringify(result).includes('processed_requests'),false)
})
test('recovery brief shows checkpoint and explicitly disclaims unverifiable sources',()=>{
 const b=recoveryBrief(state(),'T-002')
 assert.equal(b.state_version,12)
 assert.equal(b.checkpoint.next_step,'Inspect CI logs')
 assert.equal(b.checkpoint.git_sha_verified,false)
 assert.equal(b.requires_owner_approval_for_forced_takeover,true)
 assert.equal(b.takeover_authorization,'explicit_owner_authored_issue')
 assert.equal(b.requires_github_gui_approval_for_forced_takeover,false)
 assert.equal(b.can_recover_uncommitted_chat_work,false)
 assert.doesNotMatch(JSON.stringify(b),/11111111-1111/)
})
test('missing checkpoint gets an honest warning, not invented prior progress',()=>{
 const b=recoveryBrief(state(),'T-003')
 assert.equal(b.checkpoint,null)
 assert.match(b.warning,/No durable checkpoint/)
})
test('no duplicates and malformed state rejected before discoverability',()=>{
 const a=state()
 assert.throws(()=>listUnfinishedRequirements([a,a]),/DUPLICATE_REQUIREMENT/)
 a.tasks[1].depends_on=['T-999']
 assert.throws(()=>listUnfinishedRequirements([a]),e=>e.code==='UNKNOWN_DEPENDENCY')
 assert.throws(()=>recoveryBrief(state(),'T-999'),/UNKNOWN_TASK/)
})
test('local CLI reads registered requirements only, no symlink or extra file',()=>{
 const root=mkdtempSync(join(tmpdir(),'prp-recovery-'))
 mkdirSync(join(root,'requirements'))
 const req=state()
 writeFileSync(join(root,'requirements',req.requirement_id+'.json'),JSON.stringify(req))
 writeFileSync(join(root,'requirements','garbage.txt'),'untrusted')
 const loaded=loadRequirementDirectory(join(root,'requirements'))
 assert.equal(loaded.length,1)
 const p=spawnSync(process.execPath,[new URL('./recovery.mjs',import.meta.url).pathname,
   join(root,'requirements'),req.requirement_id,'T-002'],{encoding:'utf8'})
 assert.equal(p.status,0,p.stderr)
 assert.equal(JSON.parse(p.stdout).checkpoint.branch,'feature/recover')
})

test('recovery briefing labels owner-reconstructed evidence without exposing claim credentials',()=>{
 const s=state()
 s.tasks[1].checkpoint.origin='owner_verified_git'
 s.tasks[1].handoff_history=[{
   type:'takeover',from_worker:'chat-old',to_worker:'chat-new',
   at:'2026-11-01T01:50:00Z',actor:'micor-cjj-spec',
   reason:'Original session unavailable',head_sha:sha,
   previous_generation:1,generation:2
 }]
 const b=recoveryBrief(s,'T-002')
 assert.equal(b.checkpoint.checkpoint_origin,'owner_verified_git')
 assert.equal(b.checkpoint.git_sha_verified,false)
 assert.equal(b.last_handoff.from_worker,'chat-old')
 assert.equal(b.last_handoff.to_worker,'chat-new')
 assert.equal(JSON.stringify(b).includes('11111111-1111-4111'),false)
})
