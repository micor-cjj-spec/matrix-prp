import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
const deploy = readFileSync(new URL('../../.github/workflows/deploy-prp.yml', import.meta.url), 'utf8')
const impact = readFileSync(new URL('../../.github/workflows/feature-impact.yml', import.meta.url), 'utf8')
const pkceShell = readFileSync(new URL('../deploy/mcp-oauth/test_full_e2e_ci.sh', import.meta.url), 'utf8')
const pkceBrowser = readFileSync(new URL('../deploy/mcp-oauth/ci_pkce_browser.py', import.meta.url), 'utf8')
const tierInventory = JSON.parse(readFileSync(new URL('../config/ci-tier-inventory.json', import.meta.url), 'utf8'))
const legacyCimd = readFileSync(new URL('../../.github/workflows/mcp-cimd-contract.yml', import.meta.url), 'utf8')
const legacyPublicRoute = readFileSync(new URL('../../.github/workflows/mcp-public-route-preflight.yml', import.meta.url), 'utf8')

test('stale PR runs cancel within their PR, but main push and other PRs remain independent', () => {
  assert.match(ci, /concurrency:\s*\n\s*group: prp-ci-.*github\.event\.pull_request\.number \|\| github\.ref/)
  assert.match(ci, /cancel-in-progress: \$\{\{ github\.event_name == 'pull_request' \}\}/)
  assert.match(ci, /push:\s*\n\s*branches: \[main\]/)
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

test('required Feature Impact job cancels stale runs within the same PR only', () => {
  assert.match(impact, /pull_request:\s*\n\s*branches: \[main\]/)
  assert.match(impact, /group: prp-impact-\$\{\{ github\.event\.pull_request\.number \}\}/)
  assert.match(impact, /cancel-in-progress: true/)
  assert.match(impact, /\n  impact-report:\n/)
})

test('Keycloak diagnostics only inspect disposable localhost, never dump authentication payloads', () => {
  assert.match(pkceShell, /--noproxy '\*'/)
  assert.match(pkceShell, /--output \/dev\/null/)
  assert.match(pkceShell, /https:\/\/auth-e2e\.localhost\/realms\/prp-mcp\/\.well-known\/openid-configuration/)
  assert.match(pkceShell, /http:\/\/127\.0\.0\.1:18080\/realms\/prp-mcp\/\.well-known\/openid-configuration/)
  assert.doesNotMatch(pkceShell, /docker logs/)
})

test('synthetic Python OAuth browser ignores hosted-runner proxy for localhost-only services', () => {
  assert.match(pkceBrowser, /from urllib\.request import .*ProxyHandler/)
  assert.match(pkceBrowser, /build_opener\(ProxyHandler\(\{\}\), HTTPSHandler\(context=context\)/)
  assert.match(pkceBrowser, /HTTPCookieProcessor\(CookieJar\(\)\), SafeRedirect\(\)/)
  assert.match(pkceBrowser, /wait_ready\(opener, ISSUER \+ "\/\.well-known\/openid-configuration"\)/)
  assert.match(pkceBrowser, /wait_ready\(opener, "https:\/\/prp-e2e\.localhost\/api\/health"\)/)
})

test('disposable PKCE CA works with strict X509 verification, never weakening TLS checks', () => {
  assert.match(pkceShell, /-addext 'basicConstraints=critical,CA:TRUE'/)
  assert.match(pkceShell, /-addext 'keyUsage=critical,keyCertSign,cRLSign'/)
  assert.match(pkceShell, /openssl verify -x509_strict -CAfile "\$tmp\/certs\/ca\.pem" "\$tmp\/certs\/leaf\.pem"/)
  assert.doesNotMatch(pkceShell, /curl[^\n]*--insecure|curl[^\n]*\s-k\s/)
})

test('L1/L2 inventory covers every required CI job without skipping checks', () => {
  const jobPart = ci.split('\njobs:\n')[1]
  assert.ok(jobPart, 'CI jobs block required')
  const names = [...jobPart.matchAll(/^  ([a-z0-9-]+):\s*$/gm)].map(m => m[1])
  const l1 = tierInventory.levels.L1.jobs
  const l2 = tierInventory.levels.L2.jobs
  assert.deepEqual([...l1, ...l2].sort(), names.sort(), 'all CI jobs must have exactly one level')
  assert.equal(new Set([...l1, ...l2]).size, names.length)
  assert.ok(l1.includes('backend-tests') && l1.includes('web-build') && l1.includes('mobile-build'))
  assert.ok(l2.includes('db-migration-integration') && l2.includes('video-db-integration'))
  for (const context of tierInventory.required_status_contexts) {
    assert.ok(context === 'impact-report' ? impact.includes('\n  impact-report:\n') : names.includes(context),
      'required context must remain present: ' + context)
  }
  assert.deepEqual(tierInventory.matrix_jobs, {'mcp-real-pkce-e2e': 2, 'mcp-integrated-oauth-keycloak': 2})
  assert.match(ci, /\n  mcp-real-pkce-e2e:\n[\s\S]*?\n      mode: \[readonly, crud\]/)
  assert.equal(tierInventory.levels.L3.workflow, '.github/workflows/deploy-prp.yml')
  assert.match(deploy, /environment:\n      name: production/)
})

test('remove only verified dead historical branch triggers, retain active review branches', () => {
  assert.doesNotMatch(ci, /feat\/multi-user-foundation/)
  assert.match(ci, /fix\/mcp-v24-lineage-conflict-20261022/)
  assert.doesNotMatch(legacyCimd, /feat\/mcp-public-acceptance-20261024/)
  assert.match(legacyCimd, /test\/mcp-authcode-privatejwt-refresh-20261024/)
  assert.doesNotMatch(legacyPublicRoute, /feat\/mcp-public-acceptance-20261024/)
  assert.match(legacyPublicRoute, /test\/mcp-authcode-privatejwt-refresh-20261024/)
})
