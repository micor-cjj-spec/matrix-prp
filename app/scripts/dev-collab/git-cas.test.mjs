import test from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { applyCommand, CollabError } from './core.mjs'

const requirement = 'REQ-20261031-001'
const actor = { actor: 'micor-cjj-spec', now: '2026-10-31T16:00:00Z' }
const uuid = n => '00000000-0000-4000-8000-' + String(n).padStart(12, '0')
const cmd = (task, worker, n) => ({
  type: 'claim', requirement_id: requirement, task_id: task,
  worker_id: worker, request_id: uuid(n)
})
const git = (where, ...args) => execFileSync('git', ['-C', where, ...args], { encoding: 'utf8', stdio: 'pipe' })
const stateName = 'requirements/' + requirement + '.json'
function newState() {
  return {
    schema_version: 1, requirement_id: requirement, issue_number: 132,
    title: 'Parallel collaboration', status: 'ACTIVE', version: 0, processed_requests: [],
    tasks: [
      { task_id: 'T-001', issue_number: 133, title: 'Core', status: 'READY',
        depends_on: [], allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null },
      { task_id: 'T-002', issue_number: 134, title: 'Templates', status: 'READY',
        depends_on: [], allowed_paths: ['.github/ISSUE_TEMPLATE/'], claim: null }
    ]
  }
}
function setup() {
  const root = mkdtempSync(join(tmpdir(), 'prp-collab-git-'))
  const remote = join(root, 'origin.git')
  execFileSync('git', ['init', '--bare', '--initial-branch=main', remote], { stdio: 'pipe' })
  const seed = join(root, 'seed')
  execFileSync('git', ['clone', remote, seed], { stdio: 'pipe' })
  git(seed, 'config', 'user.name', 'Collab CI')
  git(seed, 'config', 'user.email', 'ci@example.invalid')
  mkdirSync(join(seed, 'requirements'))
  writeFileSync(join(seed, stateName), JSON.stringify(newState(), null, 2))
  git(seed, 'add', stateName)
  git(seed, 'commit', '-m', 'bootstrap')
  git(seed, 'push', 'origin', 'HEAD:main')
  const copies = ['a', 'b'].map(name => {
    const folder = join(root, name)
    execFileSync('git', ['clone', remote, folder], { stdio: 'pipe' })
    git(folder, 'config', 'user.name', 'Collab CI')
    git(folder, 'config', 'user.email', 'ci@example.invalid')
    return folder
  })
  return { ...Object.fromEntries(['a', 'b'].map((name, i) => [name, copies[i]])), remote }
}
function change(folder, command) {
  const file = join(folder, stateName)
  const result = applyCommand(JSON.parse(readFileSync(file, 'utf8')), command, actor)
  writeFileSync(file, JSON.stringify(result.snapshot, null, 2))
  git(folder, 'add', stateName)
  git(folder, 'commit', '-m', 'claim ' + command.task_id)
  return result
}
function push(folder) {
  return spawnSync('git', ['-C', folder, 'push', 'origin', 'HEAD:main'], {
    encoding: 'utf8'
  })
}
test('two stale independent checkouts cannot both publish a claim for same task', () => {
  const { a, b } = setup()
  change(a, cmd('T-001', 'chat-A', 1))
  change(b, cmd('T-001', 'chat-B', 2))
  assert.equal(push(a).status, 0)
  assert.notEqual(push(b).status, 0, 'non-fast-forward push MUST fail')
  git(b, 'fetch', 'origin', 'main')
  git(b, 'reset', '--hard', 'origin/main')
  const updated = JSON.parse(readFileSync(join(b, stateName), 'utf8'))
  assert.throws(() => applyCommand(updated, cmd('T-001', 'chat-B', 2), actor),
    e => e instanceof CollabError && e.code === 'TASK_NOT_READY')
})

test('retry after CAS race permits different independent task without losing first', () => {
  const { a, b } = setup()
  change(a, cmd('T-001', 'chat-A', 3))
  change(b, cmd('T-002', 'chat-B', 4))
  assert.equal(push(a).status, 0)
  assert.notEqual(push(b).status, 0)
  git(b, 'fetch', 'origin', 'main')
  git(b, 'reset', '--hard', 'origin/main')
  change(b, cmd('T-002', 'chat-B', 4))
  assert.equal(push(b).status, 0)
  git(a, 'fetch', 'origin', 'main')
  git(a, 'reset', '--hard', 'origin/main')
  const final = JSON.parse(readFileSync(join(a, stateName), 'utf8'))
  assert.equal(final.version, 2)
  assert.deepEqual(final.tasks.map(t => t.status), ['CLAIMED', 'CLAIMED'])
  assert.equal(final.processed_requests.length, 2)
})
