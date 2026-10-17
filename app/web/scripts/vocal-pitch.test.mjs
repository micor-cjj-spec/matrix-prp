import test from 'node:test'
import assert from 'node:assert/strict'
import { estimatePitch, displayNote } from '../src/utils/vocalPitch.ts'

function signal(hz, amplitude = 0.25) {
  const samples = new Float32Array(4096)
  for (let i = 0; i < samples.length; i++) samples[i] = amplitude * Math.sin(2 * Math.PI * hz * i / 44100)
  return samples
}
test('pitch estimator resolves fundamental, not octave subharmonic', () => {
  for (const expected of [110, 220, 261.63, 440, 523.25, 880]) {
    const observed = estimatePitch(signal(expected), 44100)
    assert.ok(observed !== null && Math.abs(observed - expected) < 12, String(expected) + ' -> ' + observed)
  }
  assert.equal(displayNote(440), 'A4')
})
test('silence and low amplitude are not presented as an observed note', () => {
  assert.equal(estimatePitch(new Float32Array(4096), 44100), null)
  assert.equal(estimatePitch(signal(440, 0.005), 44100), null)
})
