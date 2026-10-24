import type { PitchPoint } from '@/api/vocal'

/**
 * RMS input level used for a lightweight microphone meter.
 * This is an amplitude indicator, not a calibrated sound-pressure measurement.
 */
export function calculateRms(data: Float32Array): number {
  if (data.length === 0) return 0
  let sum = 0
  for (const value of data) sum += value * value
  return Math.sqrt(sum / data.length)
}

/** A lightweight device-local monophonic pitch estimator, not a professional assessment. */
export function estimatePitch(data: Float32Array, sampleRate: number): number | null {
  // Quiet humming and phone microphones can produce a low-amplitude signal.
  // Keep a noise gate, but do not discard ordinary soft practice at the old 0.018 RMS threshold.
  if (calculateRms(data) < 0.003 || !Number.isFinite(sampleRate) || sampleRate <= 0) return null

  const minLag = Math.floor(sampleRate / 1200)
  const maxLag = Math.min(data.length / 2, Math.ceil(sampleRate / 65))
  const window = Math.min(2048, data.length - maxLag)
  if (window <= 0 || maxLag <= minLag) return null

  const differences = new Float64Array(maxLag + 1)
  // YIN-like cumulative mean normalized difference: prefer the first good trough,
  // not the global autocorrelation peak (which often aliases one octave lower).
  for (let lag = 2; lag <= maxLag; lag++) {
    let difference = 0
    for (let i = 0; i < window; i += 2) {
      const delta = data[i] - data[i + lag]
      difference += delta * delta
    }
    differences[lag] = difference
  }

  let cumulative = 0
  const normalized = new Float64Array(maxLag + 1)
  for (let lag = 2; lag <= maxLag; lag++) {
    cumulative += differences[lag]
    normalized[lag] = cumulative > 0 ? (differences[lag] * (lag - 1)) / cumulative : 1
  }
  for (let lag = Math.max(2, minLag); lag < maxLag; lag++) {
    if (normalized[lag] < 0.13) {
      while (lag + 1 <= maxLag && normalized[lag + 1] < normalized[lag]) lag++
      const hz = sampleRate / lag
      return hz >= 65 && hz <= 1200 ? Math.round(hz * 10) / 10 : null
    }
  }
  return null
}

export function displayNote(hz: number | null): string {
  if (hz == null) return '—'
  const note = Math.round(69 + 12 * Math.log2(hz / 440))
  const labels = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B']
  return labels[((note % 12) + 12) % 12] + (Math.floor(note / 12) - 1)
}
export function lastPitchCurve(points: PitchPoint[]): string {
  const recent = points.slice(-64)
  if (recent.length < 2) return ''
  const min = 120, max = 850
  return recent.map((p, i) => (
    (i / Math.max(1, recent.length - 1) * 300).toFixed(1) + ',' +
    (100 - (Math.log2(Math.min(max, Math.max(min, p.hz)) / min) /
      Math.log2(max / min) * 100)).toFixed(1)
  )).join(' ')
}
