import test from 'node:test'
import assert from 'node:assert/strict'
import { renderBoard } from './board.mjs'
const state = () => ({
  schema_version: 1, requirement_id: 'REQ-20261031-001', issue_number: 132,
  title: 'AI & tests', status: 'ACTIVE', version: 7, processed_requests: [],
  tasks: [
    { task_id: 'T-001', issue_number: 133, title: 'Core', status: 'DONE', depends_on: [],
      allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null, pr_number: 138 },
    { task_id: 'T-002', issue_number: 134, title: 'Frontend | Tests', status: 'READY', depends_on: ['T-001'],
      allowed_paths: ['app/web/src/'], claim: null },
    { task_id: 'T-003', issue_number: 135, title: 'Next task', status: 'READY', depends_on: ['T-002'],
      allowed_paths: ['app/backend/src/'], claim: null }
  ]
})
test('board renders current tasks and dependency-blocked WAITING with actual issue IDs', () => {
  const b=renderBoard(state(),{state_sha:'a'.repeat(40)})
  assert.match(b,/Completed: \*\*1\/3\*\*/)
  assert.match(b,/State version: \*\*7\*\*/)
  assert.match(b,/T-003.*WAITING/)
  assert.match(b,/T-002.*READY/)
  assert.match(b,/#138/)
  assert.match(b,/State commit:/)
})
test('display redacts claims, request history and notes, escapes Markdown and HTML', () => {
  const s=state()
  s.title='<script>bad | title</script>'
  s.tasks[0].last_note='SECRET-NEVER-SHOW'
  s.tasks[0].claim_id='SECRET-CLAIM'
  s.processed_requests=[{request_id:'00000000-0000-4000-8000-000000000001',
    actor:'micor-cjj-spec',fingerprint:'a'.repeat(64),receipt:{some:'INTERNAL'}}]
  const b=renderBoard(s)
  assert.doesNotMatch(b,/SECRET-|INTERNAL|some:|claim_id|fingerprint/)
  assert.match(b,/&lt;script&gt;/)
  assert.match(b,/&#124;/)
})
test('invalid snapshot or source SHA cannot render an apparently reliable board', () => {
  const s=state()
  assert.throws(()=>renderBoard(s,{state_sha:'bad'}),/INVALID_STATE_SHA/)
  s.tasks[0].depends_on=['T-999']
  assert.throws(()=>renderBoard(s),e=>e.code==='UNKNOWN_DEPENDENCY')
})
