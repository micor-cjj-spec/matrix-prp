import { computed, onBeforeUnmount, ref } from 'vue'
import type { PitchPoint } from '@/api/vocal'
import { estimatePitch } from '@/utils/vocalPitch'

export function useVocalRecorder() {
  const recording = ref(false)
  const seconds = ref(0)
  const currentHz = ref<number | null>(null)
  const points = ref<PitchPoint[]>([])
  let media: MediaStream | null = null
  let recorder: MediaRecorder | null = null
  let audioContext: AudioContext | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let started = 0
  let chunks: Blob[] = []
  let stopPromise: Promise<Blob> | null = null

  const MIME = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']
  const supported = computed(() => typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' && typeof MediaRecorder !== 'undefined')

  async function start() {
    if (recording.value || !supported.value) throw new Error('当前浏览器不支持录音')
    const mimeType = MIME.find(mime => MediaRecorder.isTypeSupported(mime))
    if (!mimeType) throw new Error('浏览器没有可用的音频录制格式')
    media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false }, video: false })
    try {
      audioContext = new AudioContext()
      if (audioContext.state === 'suspended') await audioContext.resume()
      const source = audioContext.createMediaStreamSource(media)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 4096
      source.connect(analyser)
      const samples = new Float32Array(analyser.fftSize)
      chunks = []
      points.value = []
      seconds.value = 0
      currentHz.value = null
      recorder = new MediaRecorder(media, { mimeType })
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      recorder.start(1000)
      started = performance.now()
      recording.value = true
      timer = setInterval(() => {
        if (!recording.value) return
        const now = (performance.now() - started) / 1000
        seconds.value = Math.min(180, Math.round(now))
        analyser.getFloatTimeDomainData(samples)
        const hz = estimatePitch(samples, audioContext!.sampleRate)
        currentHz.value = hz
        if (hz !== null && points.value.length < 1800) {
          points.value.push({ time: Math.round(now * 100) / 100, hz })
        }
      }, 160)
    } catch (error) {
      await cleanup()
      throw error
    }
  }
  async function stop(): Promise<Blob> {
    if (stopPromise) return stopPromise
    if (!recorder || !recording.value) throw new Error('没有进行中的录音')
    const active = recorder
    stopPromise = new Promise<Blob>((resolve, reject) => {
      active.addEventListener('stop', () => {
        const result = new Blob(chunks, { type: active.mimeType })
        if (!result.size) reject(new Error('没有录到声音'))
        else resolve(result)
      }, { once: true })
      active.addEventListener('error', () => reject(new Error('录音器发生错误')), { once: true })
      active.stop()
    }).finally(async () => {
      recording.value = false
      await cleanup()
      stopPromise = null
    })
    return stopPromise
  }
  async function cleanup() {
    if (timer) clearInterval(timer)
    timer = null
    media?.getTracks().forEach(t => t.stop())
    media = null
    if (audioContext) await audioContext.close().catch(() => {})
    audioContext = null
    recorder = null
  }
  onBeforeUnmount(() => { if (recorder?.state === 'recording') recorder.stop(); void cleanup() })
  return { recording, seconds, currentHz, points, supported, start, stop }
}
