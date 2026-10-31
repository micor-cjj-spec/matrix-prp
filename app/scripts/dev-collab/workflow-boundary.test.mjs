import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const workflow = readFileSync(new URL('../../../.github/workflows/prp-collab-coordinator.yml', import.meta.url), 'utf8')
const transaction = readFileSync(new URL('./state-transaction.sh', import.meta.url), 'utf8')

test('coordinator is manual, main-only, owner-only, and avoids production permissions', () => {
  assert.match(workflow, /workflow_dispatch:/)
  assert.doesNotMatch(workflow, /pull_request_target:/)
  assert.doesNotMatch(workflow, /\bpush:\s*\n/)
  assert.doesNotMatch(workflow, /runs-on:\s*self-hosted/)
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/)
  assert.match(workflow, /github\.actor == github\.repository_owner/)
  assert.match(workflow, /ref: \$\{\{ github\.sha \}\}/)
  assert.match(workflow, /permission-contents: write/)
  assert.match(workflow, /environment: prp-collab-controller/)
  assert.match(workflow, /PRP_COLLAB_APP_PRIVATE_KEY/)
  assert.match(workflow, /state-rule-policy\.mjs/)
  assert.match(workflow, /create-github-app-token@v3/)
  assert.match(workflow, /contents: read/)
  assert.doesNotMatch(workflow, /\n      contents: write\n/)
  assert.match(workflow, /STATE_BRANCH_UNPROTECTED/)
  assert.match(workflow, /branches\/prp-collab-state/)
  assert.match(workflow, /cancel-in-progress: false/)
  assert.match(workflow, /queue: max/)
  assert.doesNotMatch(workflow, /\bproduction\s*\n|secrets\.(?!PRP_COLLAB_APP_PRIVATE_KEY)[A-Z_]+|pull-requests: write/)
})

test('transaction permits non-force state-only push and retries with fresh fetch', () => {
  assert.match(transaction, /refs\/heads\/prp-collab-state/)
  assert.match(transaction, /git fetch --no-tags origin refs\/heads\/prp-collab-state/)
  assert.match(transaction, /git -C "\$state" push origin HEAD:refs\/heads\/prp-collab-state/)
  assert.doesNotMatch(transaction, /git push .*--force|git push .* -f |git reset --hard origin\/main/)
  assert.doesNotMatch(transaction, /docker|kubectl|systemctl|ssh\s|mysql\s|psql\s/)
  assert.match(transaction, /STATE_CONTENTION_OR_PUSH_DENIED/)
})
