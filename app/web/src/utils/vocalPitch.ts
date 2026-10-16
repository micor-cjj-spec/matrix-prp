import type { PitchPoint } from '@/api/vocal'

/** A lightweight, device-local monophonic pitch estimator; not a medical or professional assessment. */
export function estimatePitch(data: Float32Array, sampleRate: number): number | null {
  let sum = 0
  for (const v of data) sum += v * v
  if (Math.sqrt(sum / data.length) < 0.018) return null
  const minLag = Math.floor(sampleRate / 1200)
  const maxLag = Math.min(data.length / 2, Math.ceil(sampleRate / 65))
  let bestLag = 0
  let bestCorrelation = 0
  for (let lag = minLag; lag <= maxLag; lag++) {
    let product = 0, left = 0, right = 0
    for (let i = 0; i < data.length - lag; i += 2) {
      const a = data[i], b = data[i + lag]
      product += a * b
      left += a * a
      right += b * b
    }
    const correlation = product / Math.sqrt(left * right + 1e-12)
    if (correlation > bestCorrelation) {
      bestCorrelation = correlation
      bestLag = lag
    }
  }
  // A strong autocorrelation peak is needed, otherwise prefer no result to a guessed note.
  if (bestCorrelation < 0.87 || !bestLag) return null
  const hz = sampleRate / bestLag
  return hz >= 65 && hz <= 1200 ? Math.round(hz * 10) / 10 : null
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
    (i / 63 * 300).toFixed(1) + ',' +
    (100 - (Math.log2(Math.min(max, Math.max(min, p.hz)) / min) /
      Math.log2(max / min) * 100)).toFixed(1)
  )).join(' ')
}
