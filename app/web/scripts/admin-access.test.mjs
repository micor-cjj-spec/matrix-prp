import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ensureAdminAccess } from '../src/router/adminAccess.ts'

test('fresh admin session loads identity before route decision', async () => {
  let lookups = 0
  const session = {
    isAuthenticated: true,
    user: null,
    async loadCurrentUser() {
      lookups++
      this.user = { administrator: true }
    },
  }
  assert.equal(await ensureAdminAccess(session), 'allowed')
  assert.equal(lookups, 1)
})

test('non-admin and expired sessions cannot enter admin page', async () => {
  const nonAdmin = { isAuthenticated: true, user: { administrator: false }, async loadCurrentUser() { throw Error('unexpected') } }
  assert.equal(await ensureAdminAccess(nonAdmin), 'forbidden')
  const expired = { isAuthenticated: false, user: null, async loadCurrentUser() { throw Error('unexpected') } }
  assert.equal(await ensureAdminAccess(expired), 'unauthenticated')
})

test('temporary profile fetch outage is not mistaken for missing privileges', async () => {
  const session = { isAuthenticated: true, user: null, async loadCurrentUser() { throw Error('offline') } }
  assert.equal(await ensureAdminAccess(session), 'unavailable')
  const router = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
  assert.match(router, /const access = await ensureAdminAccess\(authStore\)/)
  assert.match(router, /access === 'unavailable'\) return false/)
})

test('HTTP 401 clearing session during lookup requires login', async () => {
  const session = { isAuthenticated: true, user: null, async loadCurrentUser() { this.isAuthenticated = false; throw Error('expired') } }
  assert.equal(await ensureAdminAccess(session), 'unauthenticated')
})
