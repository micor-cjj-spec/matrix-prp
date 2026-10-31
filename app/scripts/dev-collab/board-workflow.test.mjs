import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const workflow=readFileSync(new URL('../../../.github/workflows/prp-collab-board.yml',import.meta.url),'utf8')
test('read-only board uses pinned reviewed source and minimal permissions',()=>{
  assert.match(workflow,/workflow_dispatch:/)
  assert.match(workflow,/github\.ref == 'refs\/heads\/main'/)
  assert.match(workflow,/ref: \$\{\{ github\.sha \}\}/)
  assert.match(workflow,/contents: read/)
  assert.match(workflow,/persist-credentials: false/)
  assert.doesNotMatch(workflow,/contents: write|issues: write|pull-requests: write|pull_request_target:/)
  assert.doesNotMatch(workflow,/git push|gh issue edit|ssh |kubectl |docker /)
  assert.match(workflow,/GITHUB_STEP_SUMMARY/)
})
