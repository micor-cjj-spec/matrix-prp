import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const workflow=readFileSync(new URL('../../../.github/workflows/prp-collab-issue-projection.yml',import.meta.url),'utf8')
const cli=readFileSync(new URL('./projection-cli.mjs',import.meta.url),'utf8')
test('Issue projection is manual-only and restricted to authenticated owner on pinned main',()=>{
  assert.match(workflow,/workflow_dispatch:/)
  assert.match(workflow,/github\.ref == 'refs\/heads\/main'/)
  assert.match(workflow,/github\.actor == github\.repository_owner/)
  assert.match(workflow,/ref: \$\{\{ github\.sha \}\}/)
  assert.match(workflow,/STATE_BRANCH_UNPROTECTED/)
  assert.match(workflow,/issues: write/)
  assert.match(workflow,/queue: max/)
  assert.doesNotMatch(workflow,/contents: write|pull-requests: write|pull_request_target:/)
})
test('Issue updater cannot edit Issue body or mutate branch or PR',()=>{
  assert.match(cli,/prp-collab-state/)
  assert.match(cli,/ISSUE_MISMATCH/)
  assert.match(cli,/STATE_REF_ADVANCED/)
  assert.doesNotMatch(cli,/update_ref|git push|gh issue edit|create_pull_request|kubectl|ssh |systemctl|mysql/)
})
