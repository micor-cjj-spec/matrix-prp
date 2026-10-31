import test from 'node:test'
import assert from 'node:assert/strict'
import { applyCommand, availableTasks, CollabError, scopesOverlap, validateSnapshot } from './core.mjs'

const requirement = 'REQ-20261031-001'
const actor = { actor: 'micor-cjj-spec', now: '2026-10-31T16:00:00Z' }
let seq = 1
const uuid = () => '00000000-0000-4000-8000-' + String(seq++).padStart(12, '0')
const make = () => ({
  schema_version: 1, requirement_id: requirement, issue_number: 132, title: 'Collaboration MVP',
  status: 'ACTIVE', version: 0, processed_requests: [],
  tasks: [
    { task_id: 'T-001', issue_number: 133, title: 'Core', status: 'READY', depends_on: [], allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null },
    { task_id: 'T-002', issue_number: 134, title: 'Templates', status: 'READY', depends_on: [], allowed_paths: ['.github/ISSUE_TEMPLATE/'], claim: null },
    { task_id: 'T-003', issue_number: 135, title: 'Coordinator', status: 'READY', depends_on: ['T-001'], allowed_paths: ['app/scripts/dev-collab/'], claim: null }
  ]
})
const command = (type, task_id, extras = {}) => ({
  requirement_id: requirement, request_id: uuid(), type, task_id, ...extras
})
const claim = (s, t, worker = 'chat-A') => {
  const c = command('claim', t, { worker_id: worker })
  const result = applyCommand(s, c, actor)
  return { state: result.snapshot, claim_id: result.receipt.claim_id, command: c }
}
const assertCode = (fn, code) => assert.throws(fn, e => e instanceof CollabError && e.code === code)

test('valid ready tasks are listed, dependency blocked tasks not offered', () => {
  assert.deepEqual(availableTasks(make()).map(t => t.task_id), ['T-001', 'T-002'])
})
test('claim produces an opaque claim and increments revision once', () => {
  const r = claim(make(), 'T-001')
  assert.match(r.claim_id, /^[0-9a-f-]{36}$/)
  assert.equal(r.state.version, 1)
  assert.equal(r.state.tasks[0].status, 'CLAIMED')
})
test('same request replay does not mint a second claim', () => {
  const r = claim(make(), 'T-001')
  const replay = applyCommand(r.state, r.command, actor)
  assert.equal(replay.receipt.claim_id, r.claim_id)
  assert.equal(replay.receipt.replayed, true)
  assert.equal(replay.snapshot.version, 1)
})
test('different authenticated actor cannot replay another actor claim', () => {
  const r = claim(make(), 'T-001')
  assertCode(() => applyCommand(r.state, r.command, { ...actor, actor: 'other-actor' }), 'REQUEST_ACTOR_MISMATCH')
})
test('request id cannot be reused with different command payload', () => {
  const r = claim(make(), 'T-001')
  assertCode(() => applyCommand(r.state, { ...r.command, worker_id: 'chat-B' }, actor), 'REQUEST_ID_COLLISION')
})
test('second session cannot claim same task', () => {
  const r = claim(make(), 'T-001')
  assertCode(() => applyCommand(r.state, command('claim', 'T-001', { worker_id: 'chat-B' }), actor), 'TASK_NOT_READY')
})
test('different independent task can be claimed concurrently', () => {
  const a = claim(make(), 'T-001')
  const b = claim(a.state, 'T-002', 'chat-B')
  assert.equal(b.state.tasks.filter(t => t.status === 'CLAIMED').length, 2)
})
test('dependencies prevent claiming downstream task', () => {
  assertCode(() => claim(make(), 'T-003'), 'DEPENDENCY_BLOCKED')
})
test('reservation blocks overlapping path even when task ids differ', () => {
  const s = make()
  s.tasks[2].depends_on = []
  const a = claim(s, 'T-001')
  assertCode(() => claim(a.state, 'T-003'), 'SCOPE_CONFLICT')
})
test('stale and foreign claim cannot start task', () => {
  const r = claim(make(), 'T-001')
  assertCode(() => applyCommand(r.state, command('start', 'T-001', { worker_id: 'chat-A', claim_id: uuid() }), actor), 'STALE_OR_FOREIGN_CLAIM')
  assertCode(() => applyCommand(r.state, command('start', 'T-001', { worker_id: 'chat-A', claim_id: r.claim_id }), { ...actor, actor: 'other-actor' }), 'STALE_OR_FOREIGN_CLAIM')
})
test('start progress pause resume and submit follow legal transitions', () => {
  const r = claim(make(), 'T-001')
  const extras = { worker_id: 'chat-A', claim_id: r.claim_id }
  let s = applyCommand(r.state, command('start', 'T-001', extras), actor).snapshot
  s = applyCommand(s, command('progress', 'T-001', { ...extras, note: 'Core implemented' }), actor).snapshot
  s = applyCommand(s, command('pause', 'T-001', extras), actor).snapshot
  s = applyCommand(s, command('resume', 'T-001', extras), actor).snapshot
  s = applyCommand(s, command('submit', 'T-001', { ...extras, pr_number: 138, head_sha: 'a'.repeat(40) }), actor).snapshot
  assert.equal(s.tasks[0].status, 'IN_REVIEW')
  assert.equal(s.tasks[0].pr_number, 138)
})
test('unverified completion and requirement close fail closed', () => {
  const r = claim(make(), 'T-001')
  const ext = { worker_id: 'chat-A', claim_id: r.claim_id }
  let s = applyCommand(r.state, command('start', 'T-001', ext), actor).snapshot
  s = applyCommand(s, command('submit', 'T-001', { ...ext, pr_number: 138, head_sha: 'a'.repeat(40) }), actor).snapshot
  assertCode(() => applyCommand(s, command('accept', 'T-001'), actor), 'REVIEW_EVIDENCE_REQUIRED')
  assertCode(() => applyCommand(s, command('close'), actor), 'REQUIREMENT_APPROVAL_REQUIRED')
})
test('release invalidates original claim', () => {
  const r = claim(make(), 'T-001')
  const ext = { worker_id: 'chat-A', claim_id: r.claim_id }
  const s = applyCommand(r.state, command('release', 'T-001', ext), actor).snapshot
  assert.equal(s.tasks[0].status, 'READY')
  assertCode(() => applyCommand(s, command('start', 'T-001', ext), actor), 'NOT_CLAIMED')
})
test('cycles, unknown dependencies and duplicate ids are rejected', () => {
  const s = make()
  s.tasks[0].depends_on = ['T-003']
  assertCode(() => validateSnapshot(s), 'DEPENDENCY_CYCLE')
  s.tasks[0].depends_on = ['T-999']
  assertCode(() => validateSnapshot(s), 'UNKNOWN_DEPENDENCY')
  s.tasks[0].depends_on = []
  s.tasks[2].task_id = 'T-001'
  assertCode(() => validateSnapshot(s), 'TASK_ID')
})
test('path traversal and broad invalid scopes fail closed', () => {
  const s = make()
  s.tasks[0].allowed_paths = ['../secrets']
  assertCode(() => validateSnapshot(s), 'ALLOWED_PATHS')
  assert.equal(scopesOverlap(['app/web/src/'], ['app/web/src/views/thing.vue']), true)
  assert.equal(scopesOverlap(['app/web/src/'], ['app/backend/src/']), false)
  assert.equal(scopesOverlap(['app/a'], ['app/ab']), false)
})
test('invalid request fields and unauthenticated context are rejected', () => {
  assertCode(() => applyCommand(make(), { ...command('claim', 'T-001', { worker_id: 'chat-A' }), force: true }, actor), 'UNEXPECTED_COMMAND_FIELD')
  assertCode(() => applyCommand(make(), command('claim', 'T-001', { worker_id: 'chat-A' }), { ...actor, actor: 'bad actor' }), 'INVALID_ACTOR')
})

test('request ledger fails closed instead of allowing an old request to be replayed after eviction', () => {
  const s = make()
  s.processed_requests = Array.from({ length: 512 }, (_, i) => ({
    request_id: '10000000-0000-4000-8000-' + String(i).padStart(12, '0'),
    actor: 'micor-cjj-spec',
    fingerprint: 'a'.repeat(64),
    receipt: { version: i + 1 }
  }))
  assertCode(() => claim(s, 'T-001'), 'REQUEST_LEDGER_FULL')
})
