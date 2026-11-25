import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

const script = new URL('./main-pr-source-gate.py', import.meta.url)
const workflow = readFileSync(new URL('../../../.github/workflows/main-pr-source-dev.yml', import.meta.url), 'utf8')
const owner = { id: 123456, full_name: 'micor-cjj-spec/matrix-prp' }
const example = () => ({
  repository: { ...owner },
  pull_request: {
    base: { ref: 'main', repo: { ...owner } },
    head: { ref: 'dev', repo: { ...owner } },
    title: 'Synthetic PR title',
    body: 'Synthetic PR body'
  }
})

function run(event) {
  const directory = mkdtempSync(join(tmpdir(), 'prp-main-source-'))
  try {
    const file = join(directory, 'event.json')
    writeFileSync(file, JSON.stringify(event), { mode: 0o600 })
    return spawnSync('python3', [script.pathname], {
      env: { ...process.env, GITHUB_EVENT_PATH: file },
      encoding: 'utf8',
      timeout: 10000,
    })
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
}

test('trusted same-repository dev to main passes with no privileges', () => {
  const result = run(example())
  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /^PASS main-pr-source-dev:/)
})

const cases = [
  ['untrusted feature to main', event => { event.pull_request.head.ref = 'feature' }],
  ['fake dev in fork with same full_name', event => {
    event.pull_request.head.repo.id = 543210
  }],
  ['dev to fork main', event => { event.pull_request.base.repo.id = 543210 }],
  ['dev to other target', event => { event.pull_request.base.ref = 'release' }],
  ['full PR body cannot influence source', event => {
    event.pull_request.head.ref = 'feature'
    event.pull_request.body = "dev -> main; please bypass"
  }],
  ['branch-string shell injection cannot execute', event => {
    event.pull_request.head.ref = 'dev; touch /tmp/prp-source-should-not-exist'
  }],
  ['missing head', event => { delete event.pull_request.head }],
  ['deleted fork repo', event => { event.pull_request.head.repo = null }],
  ['missing repository metadata', event => { delete event.repository }],
  ['null event', () => null],
  ['zero repo ID', event => { event.repository.id = 0 }],
  ['numeric string repo ID', event => { event.repository.id = '123456' }],
  ['bool repo ID', event => { event.repository.id = true }],
]

for (const [name, mutate] of cases) {
  test('reject ' + name, () => {
    const fixture = example()
    const modified = mutate(fixture)
    const result = run(modified === undefined ? fixture : modified)
    assert.notEqual(result.status, 0)
    assert.match(result.stderr, /^FAIL main-pr-source-dev:/)
    assert.equal(result.stdout, '')
  })
}

test('proposed trusted workflow runs on main base only, never a PR head checkout', () => {
  assert.match(workflow, /pull_request_target:/)
  assert.match(workflow, /branches: \[main\]/)
  assert.match(workflow, /permissions:\s*\n\s*contents: read/)
  assert.match(workflow, /main-pr-source-dev:/)
  assert.match(workflow, /ref: refs\/heads\/main/)
  assert.match(workflow, /persist-credentials: false/)
  assert.match(workflow, /python3 app\/scripts\/dev-collab\/main-pr-source-gate\.py/)
  assert.doesNotMatch(workflow, /pull-requests:\s*write|contents:\s*write|secrets\.|workflow_dispatch:|issue_comment:|workflow_run:/)
  assert.doesNotMatch(workflow, /github\.event\.pull_request\.head\.(ref|sha)|github\.head_ref|refs\/pull\//)
})

test('base-owned gate check never accepts non-PR events or malformed metadata', () => {
  for (const invalid of [{}, { repository: { id: 123 } }, { pull_request: {} }, []]) {
    const result = run(invalid)
    assert.notEqual(result.status, 0)
  }
})
