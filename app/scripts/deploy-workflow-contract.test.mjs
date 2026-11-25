import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const workflow = readFileSync(new URL('../../.github/workflows/deploy-prp.yml', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const [header, rest] = workflow.split('\n  build:\n')
assert.ok(rest, 'The workflow must have a dedicated build job')
const [build, publish] = rest.split('\n  publish:\n')
assert.ok(publish, 'The workflow must have a dedicated production publish job')


test('dev and PR CI cannot enqueue auto-deploy; main push CI remains eligible', () => {
  const trigger = header.split('  workflow_run:')[1]?.split('  workflow_dispatch:')[0]
  assert.ok(trigger, 'deploy workflow_run trigger must exist')
  assert.match(trigger, /workflows: \[CI\]/)
  assert.match(trigger, /types: \[completed\]/)
  assert.match(trigger, /branches: \[main\]/)
  assert.match(header, /workflow_dispatch:/, 'manual build, check, promote and rollback stay available')
  const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
  const impact = readFileSync(new URL('../../.github/workflows/feature-impact.yml', import.meta.url), 'utf8')
  assert.match(ci, /push:\s*\n\s*branches: \[main, dev,/)
  assert.match(ci, /pull_request:\s*\n\s*branches: \[main, dev,/)
  assert.match(impact, /pull_request:\s*\n\s*branches: \[main, dev,/)
  assert.ok(ci.includes("cancel-in-progress: ${{ github.event_name == 'pull_request' }}"),
    'only stale PR checks, never a main push CI, may be auto-cancelled')
  assert.match(impact, /group: prp-impact-\$\{\{ github\.event\.pull_request\.number \}\}/)
  assert.match(impact, /cancel-in-progress: true/)
  assert.match(header, /group: prp-production/)
  assert.match(header, /cancel-in-progress: false/)
})


test('disposable E2E emits a fixed Maven failure class but never raw build logs', () => {
  const script = readFileSync(
    new URL('../../app/deploy/mcp-oauth/test_full_e2e_ci.sh', import.meta.url), 'utf8')
  assert.match(script, /for attempt in 1 2 3; do/)
  assert.match(script, /if \.\/mvnw -B -ntp -DskipTests package/)
  assert.match(script, /"\$attempt" -lt 3 && \( "\$diagnostic" == "WRAPPER_DOWNLOAD" \|\| "\$diagnostic" == "DEPENDENCY_OR_NETWORK" \)/)
  assert.match(script, /E2E_DIAG_MAVEN_RETRY_CATEGORY=\$diagnostic ATTEMPT=\$attempt/)
  assert.match(script, /sleep "\$\(\(3 \* attempt\)\)"/)
  assert.match(script, /E2E_DIAG_MAVEN_BUILD_CATEGORY=\$diagnostic/)
  assert.match(script, /diagnostic="WRAPPER_DOWNLOAD"/)
  assert.match(script, /diagnostic="DEPENDENCY_OR_NETWORK"/)
  assert.doesNotMatch(script, /(?:cat|tail|head)\s+["']?\$tmp\/java-build\.log/)
})

test('release candidates originate only from successful main push CI', () => {
  assert.match(header, /workflow_run:\s*\n\s*workflows: \[CI\]/)
  assert.match(build, /github\.event\.workflow_run\.conclusion == 'success'/)
  assert.match(build, /github\.event\.workflow_run\.event == 'push'/)
  assert.match(build, /github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(build, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
  assert.match(build, /persist-credentials: false/)
})

test('publishing requires trusted successful main push CI or explicit manual dispatch', () => {
  const condition = publish.split('    environment:')[0]
  assert.match(condition, /github\.event_name == 'workflow_dispatch'/)
  assert.match(condition, /github\.event_name == 'workflow_run'/)
  assert.match(condition, /needs\.build\.result == 'success'/)
  assert.match(condition, /github\.event\.workflow_run\.conclusion == 'success'/)
  assert.match(condition, /github\.event\.workflow_run\.event == 'push'/)
  assert.match(condition, /github\.event\.workflow_run\.head_branch == 'main'/)
  assert.match(condition, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/)
  assert.match(condition, /github\.ref == 'refs\/heads\/main'/)
  assert.match(condition, /needs\.build\.result == 'success'/)
  assert.match(publish, /environment:\s*\n\s*name: production/)
  assert.match(header, /default: build/)
})

test('production deployment rejects stale or mismatched release artifacts', () => {
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
  assert.match(publish, /artifact_commit.*RELEASE_SHA/)
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

test('publish checks out the attested commit before downloading any release archive', () => {
  const checkout = publish.indexOf('Checkout controller manifest for the exact release commit')
  const download = publish.indexOf('name: prp-release')
  const verify = publish.indexOf('Validate artifact matches the tested main commit')
  const attestation = publish.indexOf('Verify approved production controller before deploying')
  const deploy = publish.indexOf('Deploy or operate production')
  assert.ok(checkout >= 0 && download > checkout && verify > download,
    'Checkout must finish before download and release SHA validation (checkout cleans untracked files)')
  assert.ok(attestation > verify && deploy > attestation,
    'Artifact SHA and controller hash must be checked before production operation')
  assert.equal(publish.split('Checkout controller manifest for the exact release commit').length, 2,
    'Do not add another checkout after artifact extraction')
  assert.ok(publish.indexOf('test -s release.tar.gz', deploy) > deploy, 'Deploy checks the release archive exists')
})
