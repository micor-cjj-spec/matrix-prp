import test from 'node:test'
import assert from 'node:assert/strict'
import { createVideoProgressQueue, nextVideoInFolder } from '../src/utils/videoPlayback.ts'
import { PLAYBACK_SPEEDS, validPlaybackSpeed, videoProgressPercent } from '../src/utils/videoStudy.ts'

test('autoplay is limited to the same course folder in All videos', () => {
  const list = [
    { id: 1, folderId: 10 },
    { id: 2, folderId: 20 },
    { id: 3, folderId: 10 },
    { id: 4, folderId: 20 },
  ]
  assert.equal(nextVideoInFolder(list[0], list)?.id, 3)
  assert.equal(nextVideoInFolder(list[2], list), null)
  assert.equal(nextVideoInFolder({ id: 9, folderId: 10 }, list), null)
  assert.equal(nextVideoInFolder(null, list), null)
})

test('progress saving does not block clicks, and serializes/coalesces writes per video', async () => {
  let releaseFirst
  const first = new Promise(resolve => { releaseFirst = resolve })
  const calls = []
  const enqueue = createVideoProgressQueue(async (id, position, duration) => {
    calls.push({ id, position, duration })
    if (id === 1 && position === 10) await first
  })

  assert.equal(enqueue(1, 10, 100), undefined)
  enqueue(1, 11, 100)
  enqueue(1, 15, 100)
  enqueue(2, 7, 90)
  assert.deepEqual(calls.map(c => [c.id, c.position]), [[1, 10], [2, 7]])

  releaseFirst()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(calls.map(c => [c.id, c.position]), [[1, 10], [2, 7], [1, 15]])
})

test('failed progress updates cannot prevent later saves', async () => {
  const positions = []
  const queue = createVideoProgressQueue(async (_, position) => {
    positions.push(position)
    if (position === 5) throw new Error('transient outage')
  })
  queue(1, 5, 80)
  await new Promise(resolve => setImmediate(resolve))
  queue(1, 8, 80)
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(positions, [5, 8])
})

test('3x playback is supported and invalid speeds fall back to 1x', () => {
  assert.ok(PLAYBACK_SPEEDS.includes(3))
  assert.equal(validPlaybackSpeed('3'), 3)
  assert.equal(validPlaybackSpeed(7), 1)
  assert.equal(validPlaybackSpeed(null), 1)
})

test('course progress percentages honor existing server-side duration and position', () => {
  assert.equal(videoProgressPercent({ positionSeconds: 30, durationSeconds: 120 }), 25)
  assert.equal(videoProgressPercent({ positionSeconds: 180, durationSeconds: 120 }), 100)
  assert.equal(videoProgressPercent({ positionSeconds: 10 }), null)
  assert.equal(videoProgressPercent({ positionSeconds: 0, durationSeconds: 0 }), null)
})
