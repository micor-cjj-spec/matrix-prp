import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const req = 'REQ-20261031-001'
const requestId = 'deadbeef-0000-4000-8000-000000000001'

function fixture() {
  const folder = mkdtempSync(join(tmpdir(), 'prp-collab-'))
  const dir = join(folder, 'requirements')
  mkdirSync(dir)
  const path = join(dir, req + '.json')
  writeFileSync(path, JSON.stringify({
    schema_version: 1, requirement_id: req, issue_number: 132, title: 'MVP',
    status: 'ACTIVE', version: 0, processed_requests: [], tasks: [
      { task_id: 'T-001', issue_number: 133, title: 'Core', status: 'READY',
        depends_on: [], allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null }
    ]
  }))
  return { path, result: join(folder, 'result.json') }
}
function run(f, env = {}) {
  return spawnSync(process.execPath, [new URL('./coordinator-cli.mjs', import.meta.url).pathname,
    f.path, f.result], {
    encoding: 'utf8',
    env: { ...process.env, GITHUB_ACTOR: 'micor-cjj-spec', COLLAB_ACTION: 'claim',
      COLLAB_REQ_ID: req, COLLAB_TASK_ID: 'T-001', COLLAB_REQUEST_ID: requestId,
      COLLAB_WORKER_ID: 'chat-A', ...env }
  })
}

test('CLI creates durable claim and identical replay stays idempotent', () => {
  const f = fixture()
  let p = run(f)
  assert.equal(p.status, 0, p.stderr)
  const first = JSON.parse(readFileSync(f.result, 'utf8'))
  assert.match(first.claim_id, /^[0-9a-f-]{36}$/)
  p = run(f)
  assert.equal(p.status, 0, p.stderr)
  assert.equal(JSON.parse(readFileSync(f.path, 'utf8')).version, 1)
  assert.equal(JSON.parse(readFileSync(f.result, 'utf8')).replayed, true)
})

test('CLI refuses another actor and cannot mutate saved data', () => {
  const f = fixture()
  assert.equal(run(f).status, 0)
  const before = readFileSync(f.path, 'utf8')
  const p = run(f, { GITHUB_ACTOR: 'untrusted-account' })
  assert.notEqual(p.status, 0)
  assert.match(p.stderr, /REQUEST_ACTOR_MISMATCH/)
  assert.equal(readFileSync(f.path, 'utf8'), before)
})

test('CLI rejects unsupported privilege command and leaves file unchanged', () => {
  const f = fixture()
  const before = readFileSync(f.path, 'utf8')
  const p = run(f, { COLLAB_ACTION: 'accept' })
  assert.notEqual(p.status, 0)
  assert.match(p.stderr, /UNTRUSTED_REVIEW_CONTEXT/)
  assert.equal(readFileSync(f.path, 'utf8'), before)
})

test('CLI rejects mismatched requirement path and shell-like action', () => {
  const f = fixture()
  assert.notEqual(run(f, { COLLAB_REQ_ID: 'REQ-20261031-002' }).status, 0)
  assert.notEqual(run(f, { COLLAB_ACTION: 'claim; echo unsafe' }).status, 0)
})
