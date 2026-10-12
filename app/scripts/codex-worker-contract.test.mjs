import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const workflow=readFileSync(new URL('../../.github/workflows/codex-prp-worker.yml',import.meta.url),'utf8')
test('Codex execution requires manual GitHub workflow dispatch and a hosted runner',()=>{
  assert.match(workflow,/workflow_dispatch:/)
  assert.doesNotMatch(workflow,/pull_request_target:/)
  assert.doesNotMatch(workflow,/runs-on: self-hosted/)
  assert.match(workflow,/runs-on: ubuntu-latest/)
  assert.match(workflow,/permissions:\s*\n\s*contents: read/)
})
test('Unprivileged agent never receives publisher credentials and runs tests first',()=>{
  assert.match(workflow,/persist-credentials: false/)
  assert.match(workflow,/openai\/codex-action@v1/)
  assert.match(workflow,/permission-profile: ":workspace"/)
  assert.match(workflow,/safety-strategy: drop-sudo/)
  assert.match(workflow,/git diff --check/)
  assert.match(workflow,/bash mvnw -B test/)
  assert.match(workflow,/npm run build:h5/)
  assert.match(workflow,/needs: develop/)
  assert.match(workflow,/if: \$\{\{ needs\.develop\.result == 'success' \}\}/)
  assert.match(workflow,/gh pr create/)
  assert.doesNotMatch(workflow,/gh pr merge/)
  assert.doesNotMatch(workflow,/--dangerously-bypass-approvals-and-sandbox/)
})
test('Publisher does not run untrusted modified source or touch production',()=>{
  assert.match(workflow,/git apply --check/)
  assert.match(workflow,/git apply --index/)
  assert.match(workflow,/core\.hooksPath=\/dev\/null/)
  assert.match(workflow,/app\/backend\/src\/main\/java\//)
  assert.match(workflow,/app\/web\/src\//)
  assert.doesNotMatch(workflow,/kubectl |docker compose up|systemctl restart/)
})
