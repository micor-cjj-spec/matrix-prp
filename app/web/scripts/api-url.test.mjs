import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { buildApiUrl } from '../src/api/apiUrl.ts'

const streamPath = '/ai/chat/stream'

test('development root-level API proxy', () => {
  assert.equal(buildApiUrl('/api', streamPath), '/api/ai/chat/stream')
})

test('production /prp/ API proxy and trailing slash', () => {
  assert.equal(buildApiUrl('/prp/api', streamPath), '/prp/api/ai/chat/stream')
  assert.equal(buildApiUrl('/prp/api/', streamPath), '/prp/api/ai/chat/stream')
})

test('custom HTTPS API gateway', () => {
  assert.equal(buildApiUrl('https://example.com/prp/api/', streamPath),
    'https://example.com/prp/api/ai/chat/stream')
})

test('invalid API base or relative path is rejected', () => {
  assert.throws(() => buildApiUrl('', streamPath))
  assert.throws(() => buildApiUrl('/prp/api', 'ai/chat/stream'))
})

test('SSE client uses the same API base as standard requests', () => {
  const client = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
  const ai = readFileSync(new URL('../src/api/ai.ts', import.meta.url), 'utf8')
  assert.match(client, /buildApiUrl\(apiClient\.defaults\.baseURL/)
  assert.match(ai, /fetch\(apiUrl\('\/ai\/chat\/stream'\)/)
  assert.doesNotMatch(ai, /fetch\(['"]\/api\/ai\/chat\/stream['"]/)
})
