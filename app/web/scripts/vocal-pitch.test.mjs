import test from 'node:test'
import assert from 'node:assert/strict'
import { calculateRms, estimatePitch, displayNote } from '../src/utils/vocalPitch.ts'

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

test('quiet but periodic microphone input remains detectable', () => {
  const quiet = signal(440, 0.005)
  assert.ok(calculateRms(quiet) > 0.003)
  const observed = estimatePitch(quiet, 44100)
  assert.ok(observed !== null && Math.abs(observed - 440) < 12, String(observed))
})

test('silence and near-silence are not presented as an observed note', () => {
  assert.equal(calculateRms(new Float32Array(4096)), 0)
  assert.equal(estimatePitch(new Float32Array(4096), 44100), null)
  assert.equal(estimatePitch(signal(440, 0.001), 44100), null)
})
