<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  createFolder, deleteFolder, deleteVideo, getFolders, getPlayback, getVideos, getStorageUsage, renameFolder,
  saveVideoProgress, updateVideo, uploadVideo, type VideoFolder, type VideoItem, type StorageUsage,
} from '@/api/video'

const folders = ref<VideoFolder[]>([])
const videos = ref<VideoItem[]>([])
const folderId = ref<number | null>(null)
const playing = ref<VideoItem | null>(null)
const playbackUrl = ref('')
const player = ref<HTMLVideoElement | null>(null)
const speed = ref(1)
const volume = ref(1)
const uploadPercent = ref(0)
const uploading = ref(false)
const selectedFilename = ref('')
const busy = ref(false)
const storageUsage = ref<StorageUsage | null>(null)
const usagePercent = computed(() => storageUsage.value ? Math.min(100,Math.round(storageUsage.value.bytesUsed / storageUsage.value.quotaBytes * 100)) : 0)
const lastSavedAt = ref(0)

const folderTitle = computed(() =>
  folderId.value == null ? '全部视频' : folders.value.find(f => f.id === folderId.value)?.name ?? '视频')
const orderedVideos = computed(() =>
  [...videos.value].sort((a, b) => a.title.localeCompare(b.title, 'zh-CN', { numeric: true })))
const flatFolders = computed(() => {
  const rows: { folder: VideoFolder; depth: number }[] = []
  const traverse = (parent: number | null, depth: number, ancestors: Set<number>) => {
    folders.value.filter(f => f.parentId === parent).forEach(folder => {
      if (ancestors.has(folder.id)) return
      rows.push({ folder, depth })
      traverse(folder.id, depth + 1, new Set([...ancestors, folder.id]))
    })
  }
  traverse(null, 0, new Set())
  return rows
})

function formatBytes(value: number): string {
  return value >= 1073741824 ? (value / 1073741824).toFixed(2) + ' GiB'
    : (value / 1048576).toFixed(1) + ' MiB'
}
async function loadUsage() {
  storageUsage.value = await getStorageUsage()
}
async function loadFolders() { folders.value = await getFolders() }
async function loadVideos() { videos.value = await getVideos(folderId.value) }
async function refresh() {
  busy.value = true
  try { await Promise.all([loadFolders(), loadVideos(), loadUsage()]) }
  catch { ElMessage.error('无法加载视频库') }
  finally { busy.value = false }
}
async function selectFolder(id: number | null) {
  await savePosition()
  folderId.value = id
  try { await loadVideos() } catch { ElMessage.error('加载目录失败') }
}

async function addFolder() {
  try {
    const { value } = await ElMessageBox.prompt('目录名称', '新建章节/目录', { inputPattern: /\S+/, inputErrorMessage: '请输入名称' })
    await createFolder(value, folderId.value)
    await loadFolders()
    ElMessage.success('目录创建成功')
  } catch { /* dismissed */ }
}
async function editFolder(folder: VideoFolder) {
  try {
    const { value } = await ElMessageBox.prompt('目录名称', '重命名', { inputValue: folder.name, inputPattern: /\S+/ })
    await renameFolder(folder.id, value)
    await loadFolders()
  } catch { /* dismissed */ }
}
async function removeFolder(folder: VideoFolder) {
  try {
    await ElMessageBox.confirm('仅允许删除没有子目录和视频的空目录，确定删除吗？', '删除目录')
    await deleteFolder(folder.id)
    if (folderId.value === folder.id) folderId.value = null
    await refresh()
  } catch { /* dismissed or non-empty */ }
}
async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  selectedFilename.value = file.name
  uploading.value = true
  uploadPercent.value = 0
  try {
    const video = await uploadVideo(file, folderId.value, p => { uploadPercent.value = p })
    ElMessage.success('上传成功：' + video.title)
    await Promise.all([loadVideos(), loadUsage()])
  } catch {
    ElMessage.error('上传失败。重新选择同一文件可重试未完成的上传。')
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function play(video: VideoItem) {
  await savePosition()
  try {
    const playback = await getPlayback(video.id)
    playing.value = video
    playbackUrl.value = playback.url
    lastSavedAt.value = 0
    await nextTick()
    if (player.value) {
      player.value.playbackRate = speed.value
      player.value.volume = volume.value
      void player.value.play().catch(() => {})
    }
  } catch { ElMessage.error('无法播放：请检查视频权限或文件状态') }
}
function restorePosition() {
  if (!player.value || !playing.value) return
  const at = playing.value.positionSeconds
  if (at > 0 && Number.isFinite(player.value.duration) && at < player.value.duration - 3) {
    player.value.currentTime = at
  }
}
function setSpeed(value: number) {
  speed.value = value
  if (player.value) player.value.playbackRate = value
}
function setVolume(value: number) {
  volume.value = value
  if (player.value) player.value.volume = value
}
async function savePosition() {
  if (!playing.value || !player.value) return
  const position = player.value.currentTime
  const duration = player.value.duration
  if (!Number.isFinite(position) || !Number.isFinite(duration)) return
  try {
    await saveVideoProgress(playing.value.id, position, duration)
    playing.value.positionSeconds = position
  } catch { /* Retry on next pause/timeupdate */ }
}
function periodicallySave() {
  if (Date.now() - lastSavedAt.value < 15_000) return
  lastSavedAt.value = Date.now()
  void savePosition()
}
async function nextVideo() {
  await savePosition()
  const next = orderedVideos.value[orderedVideos.value.findIndex(v => v.id === playing.value?.id) + 1]
  if (next) await play(next)
}
async function editVideo(video: VideoItem) {
  try {
    const { value } = await ElMessageBox.prompt('视频标题', '修改标题', {
      inputValue: video.title, inputPattern: /\S+/,
    })
    await updateVideo(video.id, value, video.folderId)
    await loadVideos()
  } catch { /* dismissed */ }
}
async function removeVideo(video: VideoItem) {
  try {
    await ElMessageBox.confirm('视频文件将从服务器删除且无法恢复，确定删除吗？', '删除视频', { type: 'warning' })
    await deleteVideo(video.id)
    if (playing.value?.id === video.id) { playing.value = null; playbackUrl.value = '' }
    await Promise.all([loadVideos(), loadUsage()])
  } catch { /* dismissed */ }
}
onMounted(refresh)
onBeforeUnmount(() => { void savePosition() })
</script>

<template>
  <AppLayout>
    <header class="page-header">
      <div>
        <p class="eyebrow">视频学习</p>
        <h1>我的视频学习库</h1>
        <p>建立课程目录、上传视频、调整倍速，自动保存观看位置。</p>
      </div>
    </header>

    <div class="videos-layout">
      <el-card shadow="never" class="folder-panel">
        <template #header>
          <div class="videos-actions">
            <strong>课程目录</strong>
            <el-button size="small" type="primary" plain @click="addFolder">+ 新建</el-button>
          </div>
        </template>
        <div class="folder-row" :class="{ active: folderId == null }" @click="selectFolder(null)">全部视频</div>
        <div v-for="entry in flatFolders" :key="entry.folder.id"
          class="folder-row" :class="{ active: folderId === entry.folder.id }"
          :style="{ paddingLeft: `${12 + entry.depth * 18}px` }"
          @click="selectFolder(entry.folder.id)">
          <span>📁 {{ entry.folder.name }}</span>
          <el-dropdown trigger="click" @click.stop>
            <span class="folder-menu">⋯</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="editFolder(entry.folder)">重命名</el-dropdown-item>
                <el-dropdown-item @click="removeFolder(entry.folder)">删除空目录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-card>

      <div class="videos-content">
        <el-card shadow="never">
          <template #header>
            <div class="videos-actions">
              <strong>{{ folderTitle }}</strong>
              <label class="upload-action">
                <input type="file" accept=".mp4,video/mp4" :disabled="uploading" @change="onFileChange" />
                {{ uploading ? '正在上传...' : '+ 上传 MP4 视频' }}
              </label>
            </div>
          </template>
          <div v-if="uploading" class="upload-status">
            {{ selectedFilename }} <el-progress :percentage="uploadPercent" />
          </div>
          <el-empty v-if="!busy && orderedVideos.length === 0" description="当前没有视频，可以选择目录后上传 MP4" />
          <div v-for="video in orderedVideos" :key="video.id" class="video-list-item"
            :class="{ selected: playing?.id === video.id }">
            <button class="video-title-button" @click="play(video)">
              ▶ {{ video.title }}
              <small>{{ (video.sizeBytes / 1024 / 1024).toFixed(1) }} MB
                <template v-if="video.positionSeconds > 0">· 续播 {{ Math.floor(video.positionSeconds / 60) }} 分钟</template>
              </small>
            </button>
            <el-button size="small" text @click="editVideo(video)">编辑</el-button>
            <el-button size="small" type="danger" text @click="removeVideo(video)">删除</el-button>
          </div>
        </el-card>

        <el-card v-if="storageUsage" shadow="never">
          <div class="videos-actions">
            <strong>我的视频空间</strong>
            <span>{{ formatBytes(storageUsage.bytesUsed) }} / {{ formatBytes(storageUsage.quotaBytes) }}
              （{{ storageUsage.fileCount }} 个视频）</span>
          </div>
          <el-progress :percentage="usagePercent" :stroke-width="8" :show-text="false" style="margin-top: 12px" />
        </el-card>

        <el-card shadow="never" class="video-player-panel">
          <template #header><strong>{{ playing?.title || '播放器' }}</strong></template>
          <template v-if="playing">
            <video ref="player" class="video-player" :src="playbackUrl"
              controls playsinline webkit-playsinline preload="metadata"
              @loadedmetadata="restorePosition" @timeupdate="periodicallySave"
              @pause="savePosition" @ended="nextVideo" />
            <div class="videos-actions playback-options">
              <span>倍速</span>
              <el-select :model-value="speed" style="width: 105px" @update:model-value="setSpeed">
                <el-option v-for="rate in [0.75, 1, 1.25, 1.5, 2]" :key="rate" :label="`${rate}×`" :value="rate" />
              </el-select>
              <span>音量</span>
              <el-slider :model-value="volume" :min="0" :max="1" :step="0.1" style="max-width: 150px"
                @update:model-value="setVolume" />
            </div>
            <p class="video-hint">手机 Safari 音量由设备音量键控制；续播进度会自动同步到账号。</p>
          </template>
          <el-empty v-else description="从视频列表选择一节开始观看" />
        </el-card>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.videos-layout { display: grid; grid-template-columns: 265px minmax(0, 1fr); align-items: start; gap: 18px; }
.videos-content { display: grid; gap: 18px; min-width: 0; }
.videos-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.folder-row { display: flex; justify-content: space-between; align-items: center; cursor: pointer;
  min-height: 40px; border-radius: 7px; padding: 9px 12px; color: #334155; }
.folder-row:hover, .folder-row.active { background: #eff6ff; color: #1d4ed8; }
.folder-row span:first-child { overflow: hidden; text-overflow: ellipsis; }
.folder-menu { padding: 0 7px; cursor: pointer; }
.upload-action { background: #1d4ed8; color: white; cursor: pointer; border-radius: 6px;
  padding: 9px 14px; font-size: 13px; }
.upload-action input { display: none; }
.upload-status { padding: 12px; color: #475569; }
.video-list-item { border-bottom: 1px solid #e2e8f0; display: flex; align-items: center; gap: 6px; padding: 10px 4px; }
.video-list-item.selected { background: #eff6ff; }
.video-title-button { background: none; border: 0; color: #0f172a; cursor: pointer; text-align: left; flex: 1; min-width: 0; }
.video-title-button small { display: block; color: #64748b; margin: 6px 0 0 16px; }
.video-player { display: block; width: 100%; max-height: 66vh; background: black; border-radius: 8px; }
.playback-options { justify-content: flex-start; margin-top: 15px; }
.video-hint { font-size: 13px; color: #64748b; }
@media (max-width: 980px) { .videos-layout { grid-template-columns: 1fr; } }
</style>
