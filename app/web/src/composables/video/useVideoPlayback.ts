import { computed, onBeforeUnmount, ref } from 'vue'
import { getPlayback, saveVideoProgress, type VideoItem } from '@/api/video'
import { createVideoProgressQueue, nextVideoInFolder } from '@/utils/videoPlayback'

export interface VideoProgressSnapshot {
  positionSeconds: number
  durationSeconds: number
}
export interface VideoPlayerHandle {
  captureProgress: () => VideoProgressSnapshot | null
}
const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3] as const
const RATE_KEY = 'matrix-prp:video-playback-speed'
function storedSpeed(): number {
  try {
    const n = Number(localStorage.getItem(RATE_KEY))
    return SPEEDS.some(rate => rate === n) ? n : 1
  } catch { return 1 }
}

export function useVideoPlayback(captureCurrent: () => VideoProgressSnapshot | null) {
  const playing = ref<VideoItem | null>(null)
  const playbackUrl = ref('')
  const loadingPlaybackId = ref<number | null>(null)
  const currentTime = ref(0)
  const duration = ref(0)
  const speed = ref(storedSpeed())
  const volume = ref(1)
  const progressQueue = createVideoProgressQueue(saveVideoProgress)
  let lastSavedAt = 0
  let requestSerial = 0

  const progressPercent = computed(() => duration.value > 0
    ? Math.min(100, Math.round(currentTime.value / duration.value * 100)) : null)

  function persist(videoId: number, snapshot: VideoProgressSnapshot) {
    if (!Number.isFinite(snapshot.positionSeconds) || !Number.isFinite(snapshot.durationSeconds)
      || snapshot.positionSeconds < 0 || snapshot.durationSeconds <= 0) return
    if (playing.value?.id === videoId) playing.value.positionSeconds = snapshot.positionSeconds
    progressQueue(videoId, snapshot.positionSeconds, snapshot.durationSeconds)
  }

  function saveCurrent() {
    const video = playing.value
    if (!video) return
    persist(video.id, captureCurrent() ?? {
      positionSeconds: currentTime.value, durationSeconds: duration.value,
    })
  }

  function onProgress(videoId: number, snapshot: VideoProgressSnapshot) {
    if (playing.value?.id !== videoId) return
    currentTime.value = snapshot.positionSeconds
    duration.value = snapshot.durationSeconds
    if (Date.now() - lastSavedAt >= 15_000) {
      lastSavedAt = Date.now()
      persist(videoId, snapshot)
    }
  }

  function onPause(videoId: number, snapshot: VideoProgressSnapshot) {
    persist(videoId, snapshot)
  }

  async function play(video: VideoItem) {
    saveCurrent()
    const serial = ++requestSerial
    playing.value = null
    playbackUrl.value = ''
    loadingPlaybackId.value = video.id
    try {
      const ticket = await getPlayback(video.id)
      if (serial !== requestSerial) return
      playing.value = video
      playbackUrl.value = ticket.url
      currentTime.value = video.positionSeconds || 0
      duration.value = video.durationSeconds || 0
      lastSavedAt = Date.now()
    } finally {
      if (serial === requestSerial) loadingPlaybackId.value = null
    }
  }

  function stop() {
    saveCurrent()
    ++requestSerial
    playing.value = null
    playbackUrl.value = ''
    loadingPlaybackId.value = null
    currentTime.value = 0
    duration.value = 0
  }

  async function next(playlist: readonly VideoItem[]) {
    const candidate = nextVideoInFolder(playing.value, playlist)
    if (candidate) await play(candidate)
    else saveCurrent()
  }

  async function previous(playlist: readonly VideoItem[]) {
    const video = playing.value
    if (!video) return
    const index = playlist.findIndex(item => item.id === video.id)
    const candidate = playlist.slice(0, Math.max(0, index)).reverse()
      .find(item => item.folderId === video.folderId)
    if (candidate) await play(candidate)
  }

  function changeSpeed(rate: number) {
    if (!SPEEDS.some(value => value === rate)) return
    speed.value = rate
    try { localStorage.setItem(RATE_KEY, String(rate)) } catch { /* Storage may be disabled */ }
  }

  onBeforeUnmount(stop)
  return {
    playing, playbackUrl, loadingPlaybackId, speed, volume, currentTime, duration,
    progressPercent, saveCurrent, onProgress, onPause, play, stop, next, previous,
    changeSpeed,
  }
}
