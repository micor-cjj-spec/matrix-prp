import test from 'node:test'
import assert from 'node:assert/strict'
import { safeUnauthenticatedRedirect } from '../src/router/safeUnauthenticatedRedirect.ts'

test('MCP client grant deep link never forwards authorization code/state to login', () => {
  const redirected = safeUnauthenticatedRedirect({
    name: 'mcp-client-grants',
    path: '/me/mcp-clients',
    fullPath: '/me/mcp-clients?code=synthetic-secret&state=synthetic-nonce&iss=https%3A%2F%2Fauth.invalid',
  })
  assert.equal(redirected, '/me/mcp-clients')
  assert.ok(!redirected.includes('synthetic-secret'))
  assert.ok(!redirected.includes('synthetic-nonce'))
})

test('normal non-OAuth navigation still preserves safe deep-link query', () => {
  assert.equal(safeUnauthenticatedRedirect({
    name: 'tasks', path: '/tasks', fullPath: '/tasks?filter=mine&page=2',
  }), '/tasks?filter=mine&page=2')
})

test('MCP client grant helper ignores attacker-supplied fullPath query', () => {
  assert.equal(safeUnauthenticatedRedirect({
    name: 'mcp-client-grants',
    path: '/me/mcp-clients',
    fullPath: '/me/mcp-clients?redirect=https%3A%2F%2Fevil.invalid%2F?code%3Dabc',
  }), '/me/mcp-clients')
})
