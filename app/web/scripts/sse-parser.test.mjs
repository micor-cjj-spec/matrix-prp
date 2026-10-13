import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createSseParser } from '../src/api/sseParser.ts'

test('CRLF split across arbitrary network chunks preserves all events', () => {
  const frames = []
  const parser = createSseParser(frame => frames.push(frame))
  for (const char of 'event: meta\r\ndata: {"conversationId":"42"}\r\n\r\nevent: delta\r\ndata: {"text":"ok"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n') parser.feed(char)
  assert.deepEqual(frames.map(frame => frame.event), ['meta','delta','done'])
  assert.deepEqual(JSON.parse(frames[1].data), { text: 'ok' })
})

test('UTF-8 multibyte text split by fetch chunks decodes without corruption', () => {
  const frames = []
  const parser = createSseParser(frame => frames.push(frame))
  const decoder = new TextDecoder()
  const bytes = new TextEncoder().encode('event: delta\ndata: {"text":"你好🌍"}\n\n')
  for (const byte of bytes) parser.feed(decoder.decode(Uint8Array.of(byte), { stream: true }))
  parser.feed(decoder.decode())
  assert.equal(JSON.parse(frames[0].data).text, '你好🌍')
})

test('comments and multiline data follow SSE grammar', () => {
  const frames = []
  const parser = createSseParser(frame => frames.push(frame))
  parser.feed(': heartbeat\nevent: delta\ndata: {"text":\ndata: "hello"}\n\n')
  assert.equal(frames.length, 1)
  assert.equal(JSON.parse(frames[0].data).text, 'hello')
})

test('incomplete final frame does not masquerade as completed event', () => {
  const frames = []
  const parser = createSseParser(frame => frames.push(frame))
  parser.feed('event: done\ndata: {}\n')
  assert.deepEqual(frames, [])
})

test('oversized unbounded data line is rejected', () => {
  const parser = createSseParser(() => {})
  assert.throws(() => parser.feed('x'.repeat(128 * 1024 + 1)), /too large/)
})
