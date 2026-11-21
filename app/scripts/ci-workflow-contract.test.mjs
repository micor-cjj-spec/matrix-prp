import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const ci = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
const deploy = readFileSync(new URL('../../.github/workflows/deploy-prp.yml', import.meta.url), 'utf8')
const impact = readFileSync(new URL('../../.github/workflows/feature-impact.yml', import.meta.url), 'utf8')
const pkceShell = readFileSync(new URL('../deploy/mcp-oauth/test_full_e2e_ci.sh', import.meta.url), 'utf8')
const pkceBrowser = readFileSync(new URL('../deploy/mcp-oauth/ci_pkce_browser.py', import.meta.url), 'utf8')

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
