import test from 'node:test'
import assert from 'node:assert/strict'
import {
  browserPairingConfig, createBrowserPairingRequest,
  readBrowserPairingCallback, hasOAuthCallback,
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
