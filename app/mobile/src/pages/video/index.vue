<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listFolders, listVideos, playback, saveProgress, type VideoFolder, type VideoItem } from '@/api/video'

const folders = ref<VideoFolder[]>([])
const videos = ref<VideoItem[]>([])
const currentFolderId = ref<number | null>(null)
const current = ref<VideoItem | null>(null)
const source = ref('')
const speed = ref(1)
const loading = ref(false)
const positionSeconds = ref(0)
const durationSeconds = ref(0)
const lastSavedAt = ref(0)

const flatFolders = computed(() => {
  const rows: { folder: VideoFolder; depth: number }[] = []
  const walk = (id: number | null, depth: number, visited: Set<number>) => {
    folders.value.filter(folder => folder.parentId === id).forEach(folder => {
      if (visited.has(folder.id)) return
      rows.push({ folder, depth })
      walk(folder.id, depth + 1, new Set([...visited, folder.id]))
    })
  }
  walk(null, 0, new Set())
  return rows
})
const orderedVideos = computed(() =>
  [...videos.value].sort((a, b) => a.title.localeCompare(b.title, 'zh-CN', { numeric: true })))

async function refresh() {
  loading.value = true
  try {
    const [nextFolders, nextVideos] = await Promise.all([listFolders(), listVideos(currentFolderId.value)])
    folders.value = nextFolders
    videos.value = nextVideos
  } catch {
    uni.showToast({ title: '视频目录加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
async function selectFolder(id: number | null) {
  persistProgress()
  currentFolderId.value = id
  await refresh()
}
async function play(video: VideoItem) {
  persistProgress()
  try {
    const item = await playback(video.id)
    current.value = video
    positionSeconds.value = video.positionSeconds
    durationSeconds.value = 0
    source.value = item.url
    lastSavedAt.value = 0
  } catch {
    uni.showToast({ title: '视频暂时无法播放', icon: 'none' })
  }
}
function onTimeUpdate(event: Event) {
  const detail = (event as Event & { detail?: { currentTime?: number; duration?: number } }).detail
  const element = event.target as HTMLVideoElement | null
  positionSeconds.value = detail?.currentTime ?? element?.currentTime ?? 0
  durationSeconds.value = detail?.duration ?? element?.duration ?? 0
  if (Date.now() - lastSavedAt.value > 15_000) {
    lastSavedAt.value = Date.now()
    persistProgress()
  }
}
function persistProgress() {
  if (!current.value || !Number.isFinite(positionSeconds.value)
    || !Number.isFinite(durationSeconds.value)) return
  void saveProgress(current.value.id, positionSeconds.value, durationSeconds.value).catch(() => {})
}
function changeSpeed(next: number) {
  speed.value = next
  uni.createVideoContext('courseVideo').playbackRate(next)
}
function onVideoEnded() {
  persistProgress()
  const next = orderedVideos.value[orderedVideos.value.findIndex(item => item.id === current.value?.id) + 1]
  if (next) void play(next)
}
function goHome() {
  persistProgress()
  uni.navigateBack()
}
onMounted(refresh)
</script>

<template>
  <view class="screen">
    <view class="brand-row">
      <view class="brand-mark">▶</view>
      <view>
        <view class="title">视频学习库</view>
        <text class="muted">课程章节、倍速播放、进度同步</text>
      </view>
    </view>
    <button class="button-secondary" @click="goHome">返回今日</button>

    <view class="section">
      <view class="section-title">课程目录</view>
      <scroll-view scroll-x class="video-folder-scroll">
        <view class="video-folder-row">
          <button class="video-folder-button" :class="{ selected: currentFolderId == null }"
            @click="selectFolder(null)">全部视频</button>
          <button v-for="entry in flatFolders" :key="entry.folder.id" class="video-folder-button"
            :class="{ selected: currentFolderId === entry.folder.id }"
            @click="selectFolder(entry.folder.id)">{{ entry.depth > 0 ? '└ ' : '' }}{{ entry.folder.name }}</button>
        </view>
      </scroll-view>
    </view>

    <view v-if="current" class="section">
      <view class="section-title">{{ current.title }}</view>
      <video id="courseVideo" class="video-player-mobile" :src="source" controls
        :initial-time="current.positionSeconds" playsinline :show-fullscreen-btn="true"
        @timeupdate="onTimeUpdate" @pause="persistProgress" @ended="onVideoEnded" />
      <view class="video-speed-row">
        <text class="muted">播放速度</text>
        <button v-for="rate in [0.75, 1, 1.25, 1.5, 2]" :key="rate" class="video-speed-button"
          :class="{ selected: speed === rate }" @click="changeSpeed(rate)">{{ rate }}×</button>
      </view>
      <text class="muted">iPhone 音量请使用设备音量键；退出页面前会保存学习进度。</text>
    </view>

    <view class="section">
      <view class="section-title">视频列表</view>
      <view v-if="loading" class="empty">加载中...</view>
      <view v-else-if="orderedVideos.length === 0" class="empty">暂无视频，请先使用电脑 Web 端上传 MP4。</view>
      <view v-for="item in orderedVideos" :key="item.id" class="list-card"
        @click="play(item)">
        <view>
          <text class="list-title">{{ item.title }}</text>
          <text class="muted">{{ (item.sizeBytes / 1048576).toFixed(1) }} MB
            {{ item.positionSeconds > 0 ? ' · 已看 ' + Math.floor(item.positionSeconds / 60) + ' 分钟' : '' }}</text>
        </view>
        <text class="muted">{{ current?.id === item.id ? '正在播放' : '▶' }}</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.video-folder-scroll { white-space: nowrap; }
.video-folder-row { display: flex; gap: 8px; padding: 4px 0; }
.video-folder-button { flex: 0 0 auto; min-height: 36px; padding: 0 12px;
  background: #fff; border-radius: 8px; font-size: 13px; color: #475569; }
.video-folder-button.selected { background: #1d4ed8; color: #fff; }
.video-player-mobile { width: 100%; height: 220px; background: #000; border-radius: 9px; }
.video-speed-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
.video-speed-button { flex: 0 0 auto; padding: 0 9px; min-height: 33px; font-size: 12px;
  background: #eef2ff; color: #1d4ed8; }
.video-speed-button.selected { background: #1d4ed8; color: #fff; }
</style>
