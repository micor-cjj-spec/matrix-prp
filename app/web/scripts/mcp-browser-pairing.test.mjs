import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { safeUnauthenticatedRedirect } from '../src/router/safeUnauthenticatedRedirect.ts'
import {
  browserPairingConfig, createBrowserPairingRequest,
  readBrowserPairingCallback, hasOAuthCallback, exchangeBrowserPairingToken,
} from '../src/api/mcpBrowserPairing.ts'

const config = browserPairingConfig(
  'https://auth-test.micor.top/realms/prp-mcp',
  'prp-browser-link',
  'https://prp-test.micor.top/api/mcp',
  'https://prp-test.micor.top/prp/me/mcp-clients',
)
const ticket = 'A'.repeat(43)
const now = 1792890000000

test('browser pairing refuses incomplete and unsafe OAuth configuration', () => {
  assert.equal(browserPairingConfig(undefined, 'prp-browser-link', 'https://prp-test.micor.top/api/mcp',
    'https://prp-test.micor.top/prp/me/mcp-clients'), null)
  assert.throws(() => browserPairingConfig('http://auth-test.micor.top', 'pair',
    'https://prp-test.micor.top/api/mcp', 'https://prp-test.micor.top/prp/me/mcp-clients'))
  assert.throws(() => browserPairingConfig('https://auth-test.micor.top', 'https://chatgpt.com/oauth/client.json',
    'https://prp-test.micor.top/api/mcp', 'https://prp-test.micor.top/prp/me/mcp-clients'))
  assert.throws(() => browserPairingConfig('https://auth-test.micor.top', 'pair',
    'https://prp-test.micor.top/api/foo', 'https://prp-test.micor.top/prp/me/mcp-clients'))
  assert.throws(() => browserPairingConfig('https://auth-test.micor.top', 'pair',
    'https://prp-test.micor.top/api/mcp', 'http://unsafe.example.com/me/mcp-clients'))
})

test('browser pairing uses random S256 and only read-only task scope', async () => {
  const { url, pending } = await createBrowserPairingRequest(config, ticket, now)
  const u = new URL(url)
  assert.equal(u.origin, 'https://auth-test.micor.top')
  assert.equal(u.searchParams.get('scope'), 'openid prp.tasks.read')
  assert.equal(u.searchParams.get('code_challenge_method'), 'S256')
  assert.equal(u.searchParams.get('redirect_uri'), config.redirectUri)
  assert.equal(u.searchParams.get('resource'), config.resource)
  assert.equal(u.searchParams.get('client_id'), config.clientId)
  assert.equal(u.searchParams.get('state'), pending.state)
  assert.equal(pending.ticket, ticket)
  assert.ok(!url.includes(ticket))
  assert.ok(!url.includes(pending.verifier))
  assert.ok(!url.includes('prp.finance.read'))
  const next = await createBrowserPairingRequest(config, ticket, now)
  assert.notEqual(next.pending.state, pending.state)
  const cb = config.redirectUri + '?code=abc&state=' + encodeURIComponent(pending.state) +
    '&iss=' + encodeURIComponent(config.issuer)
  assert.deepEqual(readBrowserPairingCallback(cb, config, pending, now + 60_000),
    { code: 'abc', verifier: pending.verifier, ticket })
  assert.equal(hasOAuthCallback(cb), true)
  assert.equal(hasOAuthCallback(config.redirectUri), false)
})

test('browser pairing rejects replayable, expired or substituted callback', async () => {
  const { pending } = await createBrowserPairingRequest(config, ticket, now)
  const cb = (suffix) => config.redirectUri + '?code=abc&state=' +
    encodeURIComponent(pending.state) + '&iss=' + encodeURIComponent(config.issuer) + suffix
  assert.throws(() => readBrowserPairingCallback(cb(''), config, null, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb(''), config, pending, now + 9 * 60_000))
  assert.throws(() => readBrowserPairingCallback(cb(''), config, pending, now - 1))
  assert.throws(() => readBrowserPairingCallback(cb('&state=duplicate'), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb('&iss=https://evil.invalid'), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb('').replace('&iss=', '&invalid='), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb('').replace('code=abc', 'code='), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(config.redirectUri +
    '?error=access_denied&state=' + encodeURIComponent(pending.state), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb('').replace('state=' + encodeURIComponent(pending.state),
    'state=attacker'), config, pending, now + 1000))
  assert.throws(() => readBrowserPairingCallback(cb('').replace('prp-test.micor.top', 'evil.invalid'),
    config, pending, now + 1000))
})

test('browser pairing never creates a request with invalid ticket', async () => {
  await assert.rejects(createBrowserPairingRequest(config, 'short', now))
})

test('browser token exchange is restricted to configured issuer/resource and never saves bearer', async () => {
  const savedFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return {
      ok: true,
      text: async () => JSON.stringify({ access_token: 'synthetic-test-bearer', token_type: 'Bearer' }),
    }
  }
  try {
    const token = await exchangeBrowserPairingToken(config, 'synthetic-code', 'synthetic-pkce-verifier')
    assert.equal(token, 'synthetic-test-bearer')
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'https://auth-test.micor.top/realms/prp-mcp/protocol/openid-connect/token')
    assert.equal(calls[0].options.credentials, 'omit')
    assert.equal(calls[0].options.referrerPolicy, 'no-referrer')
    assert.equal(calls[0].options.cache, 'no-store')
    const body = new URLSearchParams(calls[0].options.body)
    assert.equal(body.get('grant_type'), 'authorization_code')
    assert.equal(body.get('client_id'), config.clientId)
    assert.equal(body.get('redirect_uri'), config.redirectUri)
    assert.equal(body.get('resource'), config.resource)
    assert.equal(body.get('code'), 'synthetic-code')
    assert.equal(body.get('code_verifier'), 'synthetic-pkce-verifier')
  } finally {
    globalThis.fetch = savedFetch
  }
})

test('browser token exchange rejects non-Bearer token types and failed responses', async () => {
  const savedFetch = globalThis.fetch
  try {
    globalThis.fetch = async () => ({ ok: true, text: async () =>
      JSON.stringify({ access_token: 'fake', token_type: 'MAC' }) })
    await assert.rejects(exchangeBrowserPairingToken(config, 'code', 'verifier'))
    globalThis.fetch = async () => ({ ok: false, status: 400, text: async () => 'private' })
    await assert.rejects(exchangeBrowserPairingToken(config, 'code', 'verifier'))
  } finally {
    globalThis.fetch = savedFetch
  }
})

test('unauthenticated login redirect strips all OAuth callback parameters', () => {
  const callback = '/me/mcp-clients?code=secret&state=nonce&iss=https%3A%2F%2Fissuer'
  const cleaned = safeUnauthenticatedRedirect({
    name: 'mcp-client-grants', path: '/me/mcp-clients', fullPath: callback,
  })
  assert.equal(cleaned, '/me/mcp-clients')
  assert.ok(!cleaned.includes('secret'))
  assert.ok(!cleaned.includes('nonce'))
  assert.equal(safeUnauthenticatedRedirect({
    name: 'tasks', path: '/tasks', fullPath: '/tasks?filter=upcoming',
  }), '/tasks?filter=upcoming')
})

test('browser pairing cleanup is mandatory on failure, cancellation and callback', () => {
  const view = readFileSync(new URL('../src/views/McpClientsView.vue', import.meta.url), 'utf8')
  const router = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
  assert.match(view, /if \(grantIssued\) await revokePairingOnlyGrant\(config\.clientId\)/)
  assert.match(view, /async function cancelBrowserPairing\(\)/)
  assert.match(view, /const cleaned = await revokePairingOnlyGrant\(browserConfig\.clientId\)/)
  assert.match(view, /const revoked = browserConfig \? await revokePairingOnlyGrant\(browserConfig\.clientId\)/)
  assert.match(view, /if \(shouldCancel\) await cancelBrowserPairing\(\)/)
  assert.match(view, /v-if="pendingBrowserPairing"/)
  assert.match(view, /v-if="pairingCleanupWarning"/)
  assert.match(router, /redirect: safeUnauthenticatedRedirect\(to\)/)
})
