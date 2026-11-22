import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import test from 'node:test'

const workflow = readFileSync(
  new URL('../../../.github/workflows/prp-main-source-gate.yml', import.meta.url),
  'utf8'
)

// Exercise the exact shell from the workflow, not a duplicate implementation.
const block = workflow.match(/^        run: \|\n((?:^ {10}.*\n?)*)/m)
assert.ok(block, 'main gate must have one literal, standalone shell step')
const script = block[1].split('\n').map(line => line.startsWith('          ')
  ? line.slice(10) : line).join('\n')

function decision(input) {
  const env = {
    PATH: process.env.PATH ?? '/usr/bin:/bin',
    EVENT_NAME: input.event ?? 'pull_request_target',
    BASE_BRANCH: input.base ?? 'main',
    HEAD_BRANCH: input.head ?? 'dev',
    HEAD_REPOSITORY: input.headRepo ?? 'micor-cjj-spec/matrix-prp',
    TARGET_REPOSITORY: input.targetRepo ?? 'micor-cjj-spec/matrix-prp',
  }
  return spawnSync('bash', ['-c', script], { env, encoding: 'utf8', timeout: 2000 })
}

test('trusted main-base pull_request_target receives PR metadata as env without executing PR code', () => {
  assert.match(workflow, /pull_request_target:\s*\n\s*branches: \[main\]/)
  assert.match(workflow, /types: \[opened, reopened, synchronize, edited, ready_for_review\]/)
  assert.match(workflow, /permissions:\s*\n\s*contents: read/)
  for (const key of ['EVENT_NAME', 'BASE_BRANCH', 'HEAD_BRANCH', 'HEAD_REPOSITORY', 'TARGET_REPOSITORY']) {
    assert.match(workflow, new RegExp(`^          ${key}: \\$\\{\\{ github\\.`, 'm'))
    assert.ok(script.includes('"$' + key + '"'), 'shell must quote env ' + key)
  }
  assert.doesNotMatch(workflow, /\n  pull_request:|workflow_dispatch:|\n  push:|uses: actions\/checkout|\n\s*secrets\./)
  assert.ok(script.includes('set -euo pipefail'), 'shell must fail closed')
})

test('only the real same-repository dev to main PR source can pass', () => {
  const good = decision({})
  assert.equal(good.status, 0, good.stderr)
  assert.match(good.stdout, /PASS: main PR source/)
  for (const bad of [
    { base: 'dev' }, { base: 'release' },
    { head: 'feature/ui-v2' }, { head: 'main' },
    { headRepo: 'other-user/matrix-prp' },
    { targetRepo: 'another-owner/another-repo' },
    { event: 'push' }, { event: 'workflow_dispatch' }, { event: 'pull_request' },
    { headRepo: '' }, { targetRepo: '' },
  ]) {
    const result = decision(bad)
    assert.equal(result.status, 1, `Unexpectedly accepted ${JSON.stringify(bad)}`)
    assert.match(result.stdout, /::error::main only accepts/)
  }
})

test('PR metadata containing shell metacharacters is treated as data', () => {
  const injected = decision({ head: 'dev; echo NEVER_EXECUTE' })
  assert.equal(injected.status, 1)
  assert.doesNotMatch(injected.stdout, /NEVER_EXECUTE/)
})
