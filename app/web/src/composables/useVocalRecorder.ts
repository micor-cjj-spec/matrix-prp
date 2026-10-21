import { computed, onBeforeUnmount, ref } from 'vue'
import type { PitchPoint } from '@/api/vocal'
import { calculateRms, estimatePitch } from '@/utils/vocalPitch'

type MicrophoneTrackState = 'idle' | 'live' | 'muted' | 'ended'

export function useVocalRecorder() {
  const recording = ref(false)
  const seconds = ref(0)
  const currentHz = ref<number | null>(null)
  const points = ref<PitchPoint[]>([])
  const inputRms = ref(0)
  const peakRms = ref(0)
  const trackState = ref<MicrophoneTrackState>('idle')
  const analysisAvailable = ref(false)

  let media: MediaStream | null = null
  let recorder: MediaRecorder | null = null
  let audioContext: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let silentGain: GainNode | null = null
  let samples: Float32Array<ArrayBuffer> | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  let started = 0
  let chunks: Blob[] = []
  let stopPromise: Promise<Blob> | null = null

  const MIME = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']
  const supported = computed(() => typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' && typeof MediaRecorder !== 'undefined')

  async function start() {
    if (recording.value || !supported.value) throw new Error('当前浏览器不支持录音')
    resetMeasurements()

    try {
      // Resume AudioContext synchronously from the user gesture before awaiting the
      // iOS permission prompt. Safari may otherwise leave the analyser suspended.
      const AudioContextCtor = typeof window !== 'undefined'
        ? (window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
        : undefined
      if (AudioContextCtor) {
        try {
          audioContext = new AudioContextCtor()
          await audioContext.resume()
        } catch {
          await closeAudioContext()
        }
      }

      // Use the browser's default audio input constraints. Explicitly disabling
      // processing can select a poor/unsupported path on some mobile devices.
      media = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      const track = media.getAudioTracks().find(item => item.readyState === 'live')
      if (!track) throw new Error('没有获取到可用的麦克风音轨')
      track.enabled = true
      trackState.value = track.muted ? 'muted' : 'live'
      track.onmute = () => { trackState.value = 'muted' }
      track.onunmute = () => { trackState.value = 'live' }
      track.onended = () => { trackState.value = 'ended' }

      if (audioContext && audioContext.state !== 'closed') {
        try {
          if (audioContext.state === 'suspended') await audioContext.resume()
          const source = audioContext.createMediaStreamSource(media)
          analyser = audioContext.createAnalyser()
          analyser.fftSize = 4096
          analyser.smoothingTimeConstant = 0
          silentGain = audioContext.createGain()
          silentGain.gain.value = 0
          source.connect(analyser)
          // Keep the Web Audio graph actively rendered on Safari without
          // monitoring the microphone back through the speakers.
          analyser.connect(silentGain)
          silentGain.connect(audioContext.destination)
          samples = new Float32Array(analyser.fftSize) as Float32Array<ArrayBuffer>
          analysisAvailable.value = audioContext.state === 'running'
        } catch {
          analyser = null
          silentGain = null
          samples = null
          analysisAvailable.value = false
        }
      }

      const mimeType = MIME.find(mime => MediaRecorder.isTypeSupported(mime))
      recorder = mimeType ? new MediaRecorder(media, { mimeType }) : new MediaRecorder(media)
      chunks = []
      recorder.addEventListener('dataavailable', event => {
        if (event.data.size > 0) chunks.push(event.data)
      })
      // Do not force a timeslice: iOS Safari can emit fragmented MP4 chunks.
      // A single finalized blob is easier to preview and validate for this 3-minute limit.
      recorder.start()
      started = performance.now()
      recording.value = true
      timer = setInterval(() => {
        if (!recording.value) return
        const now = (performance.now() - started) / 1000
        seconds.value = Math.min(180, Math.floor(now))
        if (!analyser || !samples || !audioContext || audioContext.state !== 'running') {
          currentHz.value = null
          inputRms.value = 0
          return
        }
        analyser.getFloatTimeDomainData(samples)
        const rms = calculateRms(samples)
        inputRms.value = rms
        peakRms.value = Math.max(peakRms.value, rms)
        currentHz.value = estimatePitch(samples, audioContext.sampleRate)
        if (currentHz.value !== null && points.value.length < 1800) {
          points.value.push({ time: Math.round(now * 100) / 100, hz: currentHz.value })
        }
      }, 100)
    } catch (error) {
      recording.value = false
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
        const type = active.mimeType || chunks.find(chunk => chunk.type)?.type || 'application/octet-stream'
        const result = new Blob(chunks, { type })
        if (result.size === 0) reject(new Error('录音文件为空'))
        else resolve(result)
      }, { once: true })
      active.addEventListener('error', () => reject(new Error('浏览器录音器发生错误')), { once: true })
      try {
        if (active.state !== 'inactive') active.stop()
        else reject(new Error('录音器已提前停止'))
      } catch (error) {
        reject(error instanceof Error ? error : new Error('无法结束录音'))
      }
    }).finally(async () => {
      recording.value = false
      await cleanup()
      stopPromise = null
    })
    return stopPromise
  }

  function resetMeasurements() {
    seconds.value = 0
    currentHz.value = null
    points.value = []
    inputRms.value = 0
    peakRms.value = 0
    trackState.value = 'idle'
    analysisAvailable.value = false
  }

  async function closeAudioContext() {
    const active = audioContext
    audioContext = null
    analyser = null
    silentGain = null
    samples = null
    if (active && active.state !== 'closed') await active.close().catch(() => {})
  }

  async function cleanup() {
    if (timer) clearInterval(timer)
    timer = null
    media?.getTracks().forEach(track => {
      track.onmute = null
      track.onunmute = null
      track.onended = null
      track.stop()
    })
    media = null
    await closeAudioContext()
    recorder = null
    trackState.value = 'idle'
  }

  onBeforeUnmount(() => {
    if (recorder?.state === 'recording') {
      try { recorder.stop() } catch { /* page is already leaving */ }
    }
    void cleanup()
  })

  return { recording, seconds, currentHz, points, inputRms, peakRms, trackState, analysisAvailable, supported, start, stop }
}
