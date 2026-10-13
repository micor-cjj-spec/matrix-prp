import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const workflow = readFileSync(new URL('../../.github/workflows/deploy-prp.yml', import.meta.url), 'utf8')
const [header, rest] = workflow.split('\n  build:\n')
assert.ok(rest, 'The workflow must have a dedicated build job')
const [build, publish] = rest.split('\n  publish:\n')
assert.ok(publish, 'The workflow must have a dedicated production publish job')

test('release candidates originate only from successful main push CI', () => {
  assert.match(header, /workflow_run:\s*\n\s*workflows: \[CI\]/)
  assert.match(build, /github\.event\.workflow_run\.conclusion == 'success'/)
  assert.match(build, /github\.event\.workflow_run\.event == 'push'/)
  assert.match(build, /github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(build, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
  assert.match(build, /persist-credentials: false/)
})

test('successful main CI can publish automatically, but other events cannot', () => {
  assert.match(publish, /github\.event_name == 'workflow_run'/)
  assert.match(publish, /needs\.build\.result == 'success'/)
  assert.match(publish, /github\.event\.workflow_run\.conclusion == 'success'/)
  assert.match(publish, /github\.event\.workflow_run\.event == 'push'/)
  assert.match(publish, /github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(publish, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
  assert.match(publish, /environment:\s*\n\s*name: production/)
  assert.match(header, /options: \[promote, deploy, check, rollback, build\]/)
})

test('automatic deployment rejects stale or mismatched release artifacts', () => {
  assert.match(publish, /Reject stale main revision/)
  assert.match(publish, /RELEASE_SHA:/)
  assert.match(publish, /test "\$latest" = "\$RELEASE_SHA"/)
  assert.match(publish, /github\.event_name == 'workflow_run' \|\| inputs\.action == 'deploy'/)
  assert.match(publish, /artifact_commit=.*release\.json/)
  assert.match(publish, /artifact_commit.*RELEASE_SHA/)
  assert.match(publish, /ACTION:.*github\.event_name == 'workflow_run'.*'deploy'/)
})

test('promote checks candidate provenance, commit and status before production operation', () => {
  assert.match(publish, /CANDIDATE_RUN_ID/)
  assert.match(publish, /gh api "repos\/\$GITHUB_REPOSITORY\/actions\/runs\/\$CANDIDATE_RUN_ID"/)
  assert.match(publish, /\.conclusion == "success"/)
  assert.match(publish, /\.head_sha == \$sha/)
  assert.match(publish, /\.event == "workflow_run"/)
  assert.match(publish, /run-id: \$\{\{ inputs\.candidate_run_id \}\}/)
  assert.match(publish, /artifact_commit=.*release\.json/)
  assert.match(publish, /artifact_commit.*GITHUB_SHA/)
})

test('production uses existing restricted SSH and refuses unsafe rollback IDs', () => {
  assert.match(publish, /secrets\.PRP_DEPLOY_SSH_KEY/)
  assert.match(publish, /StrictHostKeyChecking=yes/)
  assert.match(publish, /prp-deploy@\$DEPLOY_HOST/)
  assert.match(publish, /rollback\)/)
  assert.match(publish, /Invalid release ID/)
})

test('server migration safety checks stay in the release helper', () => {
  const server = readFileSync(new URL('../deploy/server-release.py', import.meta.url), 'utf8')
  assert.match(server, /schema_version\(\)==db_before and schema_fingerprint\(\)==structure_before/)
  assert.match(server, /Cross-schema rollback requires operator review/)
  assert.match(server, /assert_preserved\(before,snapshot\(db\)\)/)
  assert.match(server, /run\(\['systemctl','start',SERVICE\]\)/)
})
