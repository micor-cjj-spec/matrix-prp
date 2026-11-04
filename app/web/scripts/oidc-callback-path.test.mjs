import test from 'node:test'
import assert from 'node:assert/strict'
import { isFirstPartyOidcCallbackPath } from '../src/utils/oidcCallbackPath.ts'

test('only exact callback on configured deployment base can suppress 401 login redirect', () => {
  assert.equal(isFirstPartyOidcCallbackPath('/prp/me/mcp-link/callback', '/prp/'), true)
  assert.equal(isFirstPartyOidcCallbackPath('/me/mcp-link/callback', '/'), true)
  for (const candidate of [
    '/prp/login', '/prp/me/mcp-clients', '/prp/me/mcp-link/callback/',
    '/prp/me/mcp-link/callback/extra', '/prp//me/mcp-link/callback',
    '/prp/me/mcp-link/callback%2F', '/api/mcp/link',
  ]) {
    assert.equal(isFirstPartyOidcCallbackPath(candidate, '/prp/'), false, candidate)
  }
  assert.equal(isFirstPartyOidcCallbackPath('/prp/me/mcp-link/callback', '/'), false)
  assert.equal(isFirstPartyOidcCallbackPath('/prp/me/mcp-link/callback', '/prp'), false)
  assert.equal(isFirstPartyOidcCallbackPath('/prp/me/mcp-link/callback', 'https://evil.example/'), false)
})
