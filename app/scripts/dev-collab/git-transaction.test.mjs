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

function setup({migrated=false}={}) {
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
  for (const name of ['core.mjs', 'task-scope-policy.mjs', 'review-gate.mjs', 'review-provenance.mjs', 'review-context.mjs', 'recovery-auth.mjs', 'coordinator-cli.mjs', 'state-transaction.sh']) {
    cpSync(join(source, name), join(scripts, name))
  }
  git(seed, ['add', '.'])
  git(seed, ['commit', '-m', 'test coordinator sources'])
  git(seed, ['push', '-u', 'origin', 'main'])
  const mainHead = git(seed, ['rev-parse', 'HEAD'])
  git(seed, ['checkout', '-b', 'prp-collab-state'])
  mkdirSync(join(seed, 'requirements'))
  const snapshot={
    schema_version: 1, requirement_id: reqId, issue_number: 132, title: 'local e2e',
    version: migrated?1:0, status: 'ACTIVE', processed_requests: [],
    tasks: [
      { task_id: 'T-001', issue_number: 133, title: 'core', status: 'READY', depends_on: [],
        allowed_paths: ['app/scripts/dev-collab/core.mjs'], claim: null },
      { task_id: 'T-002', issue_number: 134, title: 'templates', status: 'READY', depends_on: [],
        allowed_paths: ['.github/ISSUE_TEMPLATE/'], claim: null }
    ]
  }
  if(migrated){
    const reviewedIssueIds={3:135,4:136,5:137,6:141,7:142,8:143,9:146}
    for(let n=3;n<=9;n++)snapshot.tasks.push({
      task_id:'T-'+String(n).padStart(3,'0'),issue_number:reviewedIssueIds[n],
      title:'Synthetic reviewed V1 task '+n,status:'READY',depends_on:[],
      allowed_paths:['app/docs/dev-collab/T-'+String(n)+'.md'],claim:null
    })
  }
  writeFileSync(join(seed, 'requirements', reqId + '.json'),
    JSON.stringify(snapshot,null,2))
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
    GITHUB_SHA: '', RUNNER_TEMP: temp, COLLAB_ACTION: 'claim',
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

test('trusted manual dispatch cannot claim pristine V0 before migration', {timeout:30000}, async()=>{
 const f=setup()
 try{
  const previous=f.readState()
  const result=await run(f.workers[0],'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'T-001',{GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch'})
  assert.notEqual(result.status,0)
  assert.match(result.err,/ISSUE_MIGRATE_V1_FIRST/)
  assert.deepEqual(f.readState(),previous)
 }finally{f.destroy()}
})

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
    const c = await run(f.workers[0], id, 'T-001', { GITHUB_SHA: 'a'.repeat(40) })
    assert.notEqual(c.status, 0)
    assert.match(c.out + c.err, /SOURCE_REVISION_MISMATCH/)
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

test('two independent Git processes racing owner-approved takeover produce one new owner and fence the old claim',
  {timeout:30000},async()=>{
 const f=setup({migrated:true})
 try{
  const init=await run(f.workers[0],'77777777-7777-4777-8777-777777777777','T-001')
  assert.equal(init.status,0,init.err)
  const old=f.readState().tasks[0].claim
  const ownerEnv={COLLAB_WORKER_ID:old.worker_id,COLLAB_CLAIM_ID:old.claim_id}
  const started=await run(f.workers[0],'88888888-8888-4888-8888-888888888888',
    'T-001',{...ownerEnv,COLLAB_ACTION:'start'})
  assert.equal(started.status,0,started.err)
  const checkpoint=await run(f.workers[0],'99999999-9999-4999-8999-999999999999',
    'T-001',{...ownerEnv,COLLAB_ACTION:'checkpoint',
     COLLAB_RECOVERY_PAYLOAD:JSON.stringify({
       summary:'Pushed initial implementation',next_step:'Review changed files on GitHub',
       branch:'feature/task-core',head_sha:f.mainHead,tests:'Local contract tests passed'
     })})
  assert.equal(checkpoint.status,0,checkpoint.err)
  const current=f.readState()
  assert.equal(current.version,4)
  const common={
   GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',
   GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-coordinator.yml@refs/heads/main',
   GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_SHA:f.mainHead,
   COLLAB_ACTION:'takeover',COLLAB_WORKER_ID:old.worker_id,
   COLLAB_NOTE:'Original GPT conversation can no longer operate',
   COLLAB_RECOVERY_PAYLOAD:JSON.stringify({
     new_worker_id:'chat-rescue',expected_version:current.version,
     expected_claim_id:old.claim_id,expected_head_sha:f.mainHead
   })
  }
  const [a,b]=await Promise.all([
   run(f.workers[0],'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','T-001',common),
   run(f.workers[1],'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','T-001',common)
  ])
  assert.equal([a,b].filter(x=>x.status===0).length,1,JSON.stringify([a,b]))
  const state=f.readState()
  assert.equal(state.version,5)
  assert.equal(state.tasks[0].status,'IN_PROGRESS')
  assert.equal(state.tasks[0].claim.worker_id,'chat-rescue')
  assert.equal(state.tasks[0].claim.generation,2)
  assert.notEqual(state.tasks[0].claim.claim_id,old.claim_id)
  assert.equal(state.tasks[0].handoff_history.length,1)
  assert.equal(state.processed_requests.length,4)
  assert.equal(git(f.root,['--git-dir',f.origin,'rev-parse','refs/heads/main']),f.mainHead)
 }finally{f.destroy()}
})

test('lost original chat with zero checkpoint can be owner-reconstructed only from an existing remote feature SHA',
 {timeout:30000},async()=>{
 const f=setup({migrated:true})
 try{
  const start=await run(f.workers[0],'cccccccc-cccc-4ccc-8ccc-cccccccccccc','T-001')
  assert.equal(start.status,0,start.err)
  const original=f.readState().tasks[0].claim
  const prior=await run(f.workers[0],'dddddddd-dddd-4ddd-8ddd-dddddddddddd','T-001',{
    COLLAB_ACTION:'start',COLLAB_WORKER_ID:original.worker_id,COLLAB_CLAIM_ID:original.claim_id
  })
  assert.equal(prior.status,0,prior.err)
  git(f.root,['--git-dir',f.origin,'update-ref','refs/heads/feature/lost-chat',f.mainHead])
  const prev=f.readState()
  const fields={
    new_worker_id:'chat-restarted',expected_claim_id:original.claim_id,
    expected_version:prev.version,expected_head_sha:f.mainHead,
    checkpoint:{
      summary:'Reconstructed from remote Git branch only',
      next_step:'Inspect pushed Git diff and rerun tests',
      branch:'feature/lost-chat',head_sha:f.mainHead,
      tests:'Pending owner verification'
    }
  }
  const common={
    GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',
    GITHUB_WORKFLOW_REF:'micor-cjj-spec/matrix-prp/.github/workflows/prp-collab-coordinator.yml@refs/heads/main',
    GITHUB_REPOSITORY:'micor-cjj-spec/matrix-prp',GITHUB_SHA:f.mainHead,
    COLLAB_ACTION:'takeover',COLLAB_WORKER_ID:original.worker_id,
    COLLAB_NOTE:'Original conversation lost with no checkpoint',
    COLLAB_RECOVERY_PAYLOAD:JSON.stringify(fields)
  }
  const invalid=await run(f.workers[0],'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','T-001',{
    ...common,COLLAB_RECOVERY_PAYLOAD:JSON.stringify({...fields,checkpoint:{
      ...fields.checkpoint,head_sha:'f'.repeat(40)
    }})
  })
  assert.notEqual(invalid.status,0)
  assert.equal(f.readState().version,prev.version)
  const rescue=await run(f.workers[0],'ffffffff-ffff-4fff-8fff-ffffffffffff','T-001',common)
  assert.equal(rescue.status,0,rescue.err)
  const result=f.readState()
  assert.equal(result.version,prev.version+1)
  assert.equal(result.tasks[0].claim.worker_id,'chat-restarted')
  assert.equal(result.tasks[0].checkpoint.origin,'owner_verified_git')
  assert.equal(result.tasks[0].checkpoint.head_sha,f.mainHead)
  assert.equal(result.tasks[0].handoff_history.length,1)
  assert.equal(result.tasks[0].status,'IN_PROGRESS')
 }finally{f.destroy()}
})
