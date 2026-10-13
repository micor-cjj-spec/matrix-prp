import type { VideoItem } from '@/api/video'

export const PLAYBACK_SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3] as const

export function validPlaybackSpeed(value: unknown): number {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return PLAYBACK_SPEEDS.some(rate => rate === parsed) ? parsed : 1
}

export function videoProgressPercent(video: Pick<VideoItem, 'positionSeconds' | 'durationSeconds'>): number | null {
  const duration = video.durationSeconds
  const position = video.positionSeconds
  if (duration === undefined || !Number.isFinite(duration) || duration <= 0
    || !Number.isFinite(position) || position < 0) return null
  return Math.max(0, Math.min(100, Math.round(position / duration * 100)))
}
