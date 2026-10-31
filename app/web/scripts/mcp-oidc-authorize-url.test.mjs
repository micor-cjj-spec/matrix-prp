import test from 'node:test'
import assert from 'node:assert/strict'
import { checkedFirstPartyAuthorizeUrl } from '../src/utils/mcpOidcAuthorizeUrl.ts'

const issuer = 'https://auth-test.micor.top/realms/prp-mcp/protocol/openid-connect/auth'
const prp = 'https://prp-test.micor.top'
const base = '/prp/'
const token43 = 'A'.repeat(43)

function valid() {
  const uri = new URL(issuer)
  for (const [name, value] of Object.entries({
    response_type: 'code',
    client_id: 'prp-first-party-link',
    redirect_uri: `${prp}/prp/me/mcp-link/callback`,
    scope: 'openid',
    state: token43,
    nonce: token43,
    code_challenge: token43,
    code_challenge_method: 'S256',
  })) uri.searchParams.set(name, value)
  return uri.toString()
}

test('accept exact pinned first-party PKCE URL and reviewed PRP callback', () => {
  assert.equal(checkedFirstPartyAuthorizeUrl(valid(), issuer, prp, base), valid())
})

test('fail closed if the separately configured build-time issuer is absent', () => {
  for (const pin of ['', undefined, 'http://auth-test.micor.top/realms/prp-mcp/protocol/openid-connect/auth']) {
    assert.throws(() => checkedFirstPartyAuthorizeUrl(valid(), pin, prp, base))
  }
})

test('reject rogue callback, scope expansion, grant type and altered PKCE', () => {
  const changed = {
    response_type: 'token',
    client_id: 'https://chatgpt.com/oauth/client.json',
    redirect_uri: 'https://attacker.example/callback',
    scope: 'openid offline_access prp.finance.read',
    state: 'x',
    nonce: 'x',
    code_challenge: 'x',
    code_challenge_method: 'plain',
  }
  for (const [key, value] of Object.entries(changed)) {
    const uri = new URL(valid())
    uri.searchParams.set(key, value)
    assert.throws(
      () => checkedFirstPartyAuthorizeUrl(uri.toString(), issuer, prp, base),
      undefined,
      key,
    )
  }
})

test('reject duplicated or injected OAuth parameters even when first value is correct', () => {
  for (const key of ['client_id', 'redirect_uri', 'state', 'nonce', 'scope', 'code_challenge']) {
    const uri = new URL(valid())
    uri.searchParams.append(key, key === 'redirect_uri' ? 'https://attacker.example/callback' : 'other')
    assert.throws(() => checkedFirstPartyAuthorizeUrl(uri.toString(), issuer, prp, base), undefined, key)
  }
  const extra = new URL(valid())
  extra.searchParams.set('request_uri', 'https://attacker.example/request')
  assert.throws(() => checkedFirstPartyAuthorizeUrl(extra.toString(), issuer, prp, base))
})

test('reject wrong issuer, cross-origin auth, URL credentials, fragments and HTTP', () => {
  for (const change of [
    uri => { uri.hostname = 'attacker.example' },
    uri => { uri.pathname += '/fallback' },
    uri => { uri.username = 'someone' },
    uri => { uri.hash = '#access_token=fake' },
    uri => { uri.protocol = 'http:' },
  ]) {
    const uri = new URL(valid())
    change(uri)
    assert.throws(() => checkedFirstPartyAuthorizeUrl(uri.toString(), issuer, prp, base))
  }
})

test('reject incorrect PRP host, unsafe app base, or non-HTTPS callback origin', () => {
  for (const [origin, appBase] of [
    ['https://other.micor.top', '/prp/'],
    [prp, '/'],
    [prp, '/prp/../'],
    [prp, '//evil/'],
    ['http://prp-test.micor.top', '/prp/'],
  ]) {
    assert.throws(() => checkedFirstPartyAuthorizeUrl(valid(), issuer, origin, appBase))
  }
})
