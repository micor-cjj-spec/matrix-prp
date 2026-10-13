import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { isUserSessionExpired } from '../src/utils/authSession.ts'

test('only HTTP 401 from profile validation invalidates a stored session', () => {
  assert.equal(isUserSessionExpired({ response: { status: 401 } }), true)
  for (const error of [
    new TypeError('Failed to fetch'),
    { code: 'ECONNABORTED' },
    { response: { status: 500 } },
    { response: { status: 503 } },
    { response: { status: 403 } },
    null,
  ]) {
    assert.equal(isUserSessionExpired(error), false)
  }
})

test('auth initialization keeps token after transient profile error', () => {
  const store = readFileSync(new URL('../src/stores/auth.ts', import.meta.url), 'utf8')
  const bootstrap = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8')
  assert.match(store, /if \(token\.value === expectedToken && isUserSessionExpired\(error\)\) logout\(\)/)
  assert.doesNotMatch(bootstrap, /loadCurrentUser\(\)\.catch\(\(\) => \{\s*authStore\.logout\(\)/)
})
