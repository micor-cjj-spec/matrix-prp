import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'

const reqId = 'REQ-20261031-001'
const source = fileURLToPath(new URL('.', import.meta.url))

function git(cwd, args) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8', timeout: 10000 })
  assert.equal(result.status, 0, `git ${args.join(' ')} failed: ${result.stderr}`)
  return result.stdout.trim()
}

function setup() {
  const root = mkdtempSync(join(tmpdir(), 'prp-collab-localgit-'))
  const origin = join(root, 'origin.git')
  const seed = join(root, 'seed')
  mkdirSync(seed)
  git(root, ['init', '--bare', '--initial-branch=main', origin])
  git(seed, ['init', '--initial-branch=main'])
  git(seed, ['config', 'user.name', 'MVP Test'])
  git(seed, ['config', 'user.email', 'mvp@example.invalid'])
  git(seed, ['remote', 'add', 'origin', origin])
  const scripts = join(seed, 'app/scripts/dev-collab')
  mkdirSync(scripts, { recursive: true })
  for (const name of ['core.mjs', 'coordinator-cli.mjs', 'state-transaction.sh']) {
    cpSync(join(source, name), join(scripts, name))
  }
  git(seed, ['add', '.'])
  git(seed, ['commit', '-m', 'test coordinator sources'])
  git(seed, ['push', '-u', 'origin', 'main'])
  const mainHead = git(seed, ['rev-parse', 'HEAD'])
  git(seed, ['checkout', '-b', 'prp-collab-state'])
  mkdirSync(join(seed, 'requirements'))
  writeFileSync(join(seed, 'requirements', reqId + '.json'), JSON.stringify({
    schema_version: 1, requirement_id: reqId, issue_number: 132, title: 'local e2e',
    version: 0, status: 'ACTIVE', processed_requests: [],
    tasks: [
      { task_id: 'T-001', issue_number: 133, title: 'core', status: 'READY', depends_on: [],
        allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null },
      { task_id: 'T-002', issue_number: 134, title: 'templates', status: 'READY', depends_on: [],
        allowed_paths: ['.github/ISSUE_TEMPLATE/'], claim: null }
    ]
  }, null, 2))
  git(seed, ['add', 'requirements'])
  git(seed, ['commit', '-m', 'test-only state'])
  git(seed, ['push', 'origin', 'prp-collab-state'])
  const workers = [join(root, 'workerA'), join(root, 'workerB')]
  for (const worker of workers) {
    git(root, ['clone', '--branch', 'main', origin, worker])
  }
  return {
    root, origin, workers, mainHead,
    readState() {
      return JSON.parse(git(root, ['--git-dir', origin, 'show', 'refs/heads/prp-collab-state:requirements/' + reqId + '.json']))
    },
    destroy() { rmSync(root, { recursive: true, force: true }) }
  }
}

function commandEnvironment(worker, id, taskId, overrides = {}) {
  const temp = join(worker, 'temporary')
  mkdirSync(temp, { recursive: true })
  return {
    ...process.env, GITHUB_REF: 'refs/heads/main',
    GITHUB_ACTOR: 'micor-cjj-spec', GITHUB_REPOSITORY_OWNER: 'micor-cjj-spec',
    RUNNER_TEMP: temp, COLLAB_ACTION: 'claim',
    COLLAB_REQ_ID: reqId, COLLAB_TASK_ID: taskId,
    COLLAB_REQUEST_ID: id, COLLAB_WORKER_ID: 'chat-' + taskId,
    ...overrides
  }
}

function run(worker, id, taskId, overrides = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn('bash', ['app/scripts/dev-collab/state-transaction.sh'], {
      cwd: worker, env: commandEnvironment(worker, id, taskId, overrides)
    })
    let out = '', err = ''
    child.stdout.on('data', d => { out += d.toString() })
    child.stderr.on('data', d => { err += d.toString() })
    child.on('error', reject)
    child.on('close', status => resolve({ status, out, err }))
  })
}

test('two independent Git processes competing on one task cannot both commit a claim', { timeout: 30000 }, async () => {
  const f = setup()
  try {
    const [a, b] = await Promise.all([
      run(f.workers[0], '11111111-1111-4111-8111-111111111111', 'T-001'),
      run(f.workers[1], '22222222-2222-4222-8222-222222222222', 'T-001')
    ])
    assert.equal([a, b].filter(r => r.status === 0).length, 1, JSON.stringify([a, b]))
    assert.equal([a, b].filter(r => r.status !== 0).length, 1)
    const state = f.readState()
    assert.equal(state.version, 1)
    assert.equal(state.tasks[0].status, 'CLAIMED')
    assert.equal(state.processed_requests.length, 1)
    assert.equal(git(f.root, ['--git-dir', f.origin, 'rev-parse', 'refs/heads/main']), f.mainHead)
  } finally { f.destroy() }
})

test('two non-overlapping tasks can be claimed in separate Git processes without lost updates', { timeout: 30000 }, async () => {
  const f = setup()
  try {
    const [a, b] = await Promise.all([
      run(f.workers[0], '33333333-3333-4333-8333-333333333333', 'T-001'),
      run(f.workers[1], '44444444-4444-4444-8444-444444444444', 'T-002')
    ])
    assert.equal(a.status, 0, a.err)
    assert.equal(b.status, 0, b.err)
    const state = f.readState()
    assert.equal(state.version, 2)
    assert.deepEqual(state.tasks.map(t => t.status), ['CLAIMED', 'CLAIMED'])
    assert.equal(state.processed_requests.length, 2)
  } finally { f.destroy() }
})

test('real Git workflow rejects unauthorized actor and wrong ref before writing', { timeout: 30000 }, async () => {
  const f = setup()
  try {
    const id = '55555555-5555-4555-8555-555555555555'
    const a = await run(f.workers[0], id, 'T-001', { GITHUB_ACTOR: 'external' })
    const b = await run(f.workers[1], id, 'T-001', { GITHUB_REF: 'refs/heads/feature' })
    assert.notEqual(a.status, 0)
    assert.notEqual(b.status, 0)
    assert.equal(f.readState().version, 0)
  } finally { f.destroy() }
})

test('same request rerun in Git coordinator keeps exactly one claim commit', { timeout: 30000 }, async () => {
  const f = setup()
  try {
    const id = '66666666-6666-4666-8666-666666666666'
    const first = await run(f.workers[0], id, 'T-001')
    assert.equal(first.status, 0, first.err)
    const repeated = await run(f.workers[0], id, 'T-001')
    assert.equal(repeated.status, 0, repeated.err)
    assert.match(repeated.out, /PRP_COLLAB_IDEMPOTENT_REPLAY=YES/)
    assert.equal(f.readState().version, 1)
  } finally { f.destroy() }
})
