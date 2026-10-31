import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const workflow = readFileSync(new URL('../../../.github/workflows/prp-collab-coordinator.yml', import.meta.url), 'utf8')
const shell = readFileSync(new URL('./state-transaction.sh', import.meta.url), 'utf8')
test('coordinator can only be manually dispatched from reviewed main by repository owner', () => {
  assert.match(workflow, /workflow_dispatch:/)
  assert.doesNotMatch(workflow, /pull_request_target:|workflow_run:/)
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/)
  assert.match(workflow, /github\.actor == github\.repository_owner/)
  assert.match(workflow, /ref: main/)
  assert.match(workflow, /cancel-in-progress: false/)
})
test('controller cannot execute privileged task commands or production operations', () => {
  assert.match(shell, /OWNER_ONLY/)
  assert.match(shell, /git fetch --no-tags origin refs\/heads\/prp-collab-state/)
  assert.match(shell, /git -C "\$state" push origin HEAD:refs\/heads\/prp-collab-state/)
  assert.doesNotMatch(shell + workflow, /push origin HEAD:refs\/heads\/main|--force|ssh |kubectl |systemctl |docker compose up|pull_request_target:/)
  assert.doesNotMatch(workflow, /issues: write|actions: write/)
})
