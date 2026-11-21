import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
const deploy = readFileSync(new URL('../../.github/workflows/deploy-prp.yml', import.meta.url), 'utf8')

test('stale PR runs cancel within their PR, but main push and other PRs remain independent', () => {
  assert.match(ci, /concurrency:\s*\n\s*group: prp-ci-.*github\.event\.pull_request\.number \|\| github\.ref/)
  assert.match(ci, /cancel-in-progress: \$\{\{ github\.event_name == 'pull_request' \}\}/)
  assert.match(ci, /push:\s*\n\s*branches: \[main,/)
})

test('every existing required check keeps its stable job name and no job-level gate', () => {
  for (const job of ['backend-tests', 'web-build', 'mobile-build', 'video-db-integration', 'db-migration-integration']) {
    const marker = '\n  ' + job + ':\n'
    assert.ok(ci.includes(marker), job + ' must remain a stable required status check')
    const body = ci.split(marker)[1].split(/\n  [\w-]+:\n/)[0]
    assert.doesNotMatch(body, /^    if:/m, job + ' must not be silently skipped')
  }
})

test('production workflow does not run on PR CI completion', () => {
  assert.match(deploy, /workflow_run:\s*\n\s*workflows: \[CI\]\s*\n\s*types: \[completed\][\s\S]*?branches: \[main\]/)
  assert.match(deploy, /github\.event\.workflow_run\.event == 'push'/)
  assert.match(deploy, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
  assert.match(deploy, /cancel-in-progress: false/)
})
