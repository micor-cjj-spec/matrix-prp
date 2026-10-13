<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { VideoItem } from '@/api/video'
import type { VideoProgressSnapshot } from '@/composables/video/useVideoPlayback'
import { PLAYBACK_SPEEDS } from '@/utils/videoStudy'

const props = defineProps<{
  video: VideoItem | null
  src: string
  speed: number
  volume: number
  loading?: boolean
}>()
const emit = defineEmits<{
  progress: [videoId: number, snapshot: VideoProgressSnapshot]
  pause: [videoId: number, snapshot: VideoProgressSnapshot]
  ended: []
  'speed-change': [value: number]
  'volume-change': [value: number]
}>()
const media = ref<HTMLVideoElement | null>(null)
const videoKey = computed(() => props.video?.id ?? 'empty')

function captureProgress(): VideoProgressSnapshot | null {
  const video = media.value
  if (!video || !Number.isFinite(video.currentTime) || !Number.isFinite(video.duration)) return null
  return { positionSeconds: video.currentTime, durationSeconds: video.duration }
}
defineExpose({ captureProgress })

function emitSnapshot(event: 'progress' | 'pause') {
  const snapshot = captureProgress()
  if (!snapshot || props.video === null) return
  if (event === 'progress') emit('progress', props.video.id, snapshot)
  else emit('pause', props.video.id, snapshot)
}

function restorePosition() {
  const video = media.value
  if (!video) return
  const resume = props.video?.positionSeconds ?? 0
  if (resume > 0 && Number.isFinite(video.duration) && resume < video.duration - 3) {
    video.currentTime = resume
  }
  video.playbackRate = props.speed
  video.volume = props.volume
  void nextTick(() => { void video.play().catch(() => { /* Autoplay may be blocked */ }) })
}
watch(() => props.speed, value => { if (media.value) media.value.playbackRate = value })
watch(() => props.volume, value => { if (media.value) media.value.volume = value })
</script>

<template>
  <section class="study-player-card" aria-label="视频播放器">
    <div class="study-video-stage">
      <video v-if="video && src" :key="videoKey" ref="media" :src="src"
        class="study-video" controls playsinline webkit-playsinline preload="metadata"
        @loadedmetadata="restorePosition" @timeupdate="emitSnapshot('progress')"
        @pause="emitSnapshot('pause')" @ended="emit('ended')">
        您的浏览器暂不支持 HTML5 视频播放。
      </video>
      <div v-else class="study-video-placeholder" role="status">
        <div class="study-play-symbol">{{ loading ? '···' : '▶' }}</div>
        <strong>{{ loading ? '正在获取播放地址…' : '准备开始学习' }}</strong>
        <span>{{ loading ? '正在连接私有视频资源' : '从右侧课程目录选择一个视频' }}</span>
      </div>
    </div>
    <div class="study-player-controls">
      <div class="player-setting">
        <label for="study-speed">播放倍速</label>
        <el-select id="study-speed" :model-value="speed" aria-label="播放倍速" size="small" style="width:100px"
          @update:model-value="(value: number) => emit('speed-change', Number(value))">
          <el-option v-for="rate in PLAYBACK_SPEEDS" :key="rate" :value="rate" :label="rate + '×'" />
        </el-select>
      </div>
      <div class="player-setting volume-control">
        <label>音量</label>
        <el-slider :model-value="volume" :min="0" :max="1" :step="0.05"
          aria-label="音量" style="width:106px" @update:model-value="(value: number) => emit('volume-change', Number(value))" />
      </div>
      <span class="player-tip">进度自动同步 · 最高 3×</span>
    </div>
  </section>
</template>

<style scoped>
.study-player-card{background:#141a29;color:#fff;border-radius:13px;overflow:hidden;box-shadow:0 10px 30px rgba(17,26,49,.11)}
.study-video-stage{width:100%;aspect-ratio:16/9;background:#0c111c;display:grid;place-items:center}
.study-video{width:100%;height:100%;display:block;object-fit:contain}
.study-video-placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:11px;color:#c8d4e8;text-align:center;font-size:13px}
.study-play-symbol{display:grid;place-items:center;border-radius:50%;background:rgba(102,150,240,.16);width:72px;height:72px;color:#87b4ff;font-size:29px}
.study-video-placeholder strong{font-size:17px;font-weight:650}
.study-video-placeholder span{font-size:12px;color:#8292ad}
.study-player-controls{min-height:54px;display:flex;align-items:center;gap:22px;padding:10px 17px;background:#192237;flex-wrap:wrap}
.player-setting{display:flex;align-items:center;gap:10px}.player-setting label{font-size:12px;color:#bccadd;white-space:nowrap}
.player-tip{margin-left:auto;font-size:11px;color:#8e9cb3}
@media(max-width:620px){.study-player-card{border-radius:10px}.study-player-controls{gap:12px;padding:11px}.player-tip{display:none}}
</style>
