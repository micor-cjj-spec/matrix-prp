import test from 'node:test'
import assert from 'node:assert/strict'
import { renderProjection, chooseProjection } from './projection.mjs'
const snapshot=()=>({schema_version:1,requirement_id:'REQ-20261031-001',
  issue_number:132,title:'Collab MVP',version:4,status:'ACTIVE',processed_requests:[],
  tasks:[{task_id:'T-001',issue_number:133,title:'Core',status:'READY',
    depends_on:[],allowed_paths:['app/scripts/dev-collab/'],claim:null}]})
const sha='a'.repeat(40)
test('new projection produces pinned and redacted status board',()=>{
  const s=snapshot()
  s.processed_requests=[{request_id:'00000000-0000-4000-8000-000000000001',
    fingerprint:'b'.repeat(64),actor:'micor-cjj-spec',receipt:{claim_id:'NEVER_SHOW'}}]
  const p=renderProjection(s,sha)
  assert.match(p,/prp-collab-version:4/)
  assert.match(p,/T-001/)
  assert.match(p,/State commit:/)
  assert.doesNotMatch(p,/NEVER_SHOW|claim_id|fingerprint/)
})
test('no bot comment: create; existing identical: no-op; older: update',()=>{
  const body=renderProjection(snapshot(),sha)
  assert.deepEqual(chooseProjection([], 'REQ-20261031-001',4,body),{action:'create'})
  const old=body.replace('prp-collab-version:4','prp-collab-version:3')
  const c={id:91,user:{login:'github-actions[bot]'},body:old}
  assert.deepEqual(chooseProjection([c],'REQ-20261031-001',4,body),{action:'update',id:91})
  assert.deepEqual(chooseProjection([{...c,body}],'REQ-20261031-001',4,body),{action:'unchanged',id:91})
})
test('foreign user cannot impersonate existing official bot projection',()=>{
  const body=renderProjection(snapshot(),sha)
  const forged={id:12,user:{login:'another-user'},body}
  assert.deepEqual(chooseProjection([forged],'REQ-20261031-001',4,body),{action:'create'})
})
test('ambiguous or stale comment blocks write',()=>{
  const body=renderProjection(snapshot(),sha)
  const c={id:91,user:{login:'github-actions[bot]'},body}
  assert.throws(()=>chooseProjection([c,c],'REQ-20261031-001',4,body),/AMBIGUOUS_PROJECTION_COMMENTS/)
  const newer={...c,body:body.replace('prp-collab-version:4','prp-collab-version:5')}
  assert.throws(()=>chooseProjection([newer],'REQ-20261031-001',4,body),/STALE_PROJECTION_ATTEMPT/)
})
