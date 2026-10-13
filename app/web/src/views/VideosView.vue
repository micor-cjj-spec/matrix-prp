<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import type { VideoFolder, VideoItem } from '@/api/video'
import VideoHeader from '@/components/video/VideoHeader.vue'
import VideoPlayer from '@/components/video/VideoPlayer.vue'
import VideoPlaylist from '@/components/video/VideoPlaylist.vue'
import VideoStudyInfo from '@/components/video/VideoStudyInfo.vue'
import VideoStudyTabs from '@/components/video/VideoStudyTabs.vue'
import VideoLibraryManager from '@/components/video/VideoLibraryManager.vue'
import VideoUploadDialog from '@/components/video/VideoUploadDialog.vue'
import { useVideoLibrary } from '@/composables/video/useVideoLibrary'
import { useVideoPlayback, type VideoPlayerHandle } from '@/composables/video/useVideoPlayback'
import { useVideoUpload } from '@/composables/video/useVideoUpload'
import { nextVideoInFolder } from '@/utils/videoPlayback'

const library = useVideoLibrary()
const playerRef = ref<VideoPlayerHandle | null>(null)
const playback = useVideoPlayback(() => playerRef.value?.captureProgress() ?? null)
const uploads = useVideoUpload()
const managerOpen = ref(false)
const uploadOpen = ref(false)

const hasNext = computed(() => nextVideoInFolder(
  playback.playing.value, library.orderedVideos.value) !== null)
const hasPrevious = computed(() => {
  const current = playback.playing.value
  if (!current) return false
  const index = library.orderedVideos.value.findIndex(item => item.id === current.id)
  return index > 0 && library.orderedVideos.value.slice(0, index)
    .some(item => item.folderId === current.folderId)
})

onMounted(async () => {
  const results = await Promise.allSettled([library.refresh(), uploads.refreshUsage()])
  if (results[0].status === 'rejected') ElMessage.error('视频目录加载失败，请重试')
  if (results[1].status === 'rejected') ElMessage.warning('视频空间信息暂时无法读取')
})
onBeforeUnmount(library.dispose)

function changeFolder(id: number | null) {
  if (id === library.selectedFolderId.value) return
  playback.stop() // Save the previous video's snapshot without waiting for the API.
  void library.selectFolder(id).catch(() => ElMessage.error('目录加载失败，请重试'))
}

function changeVideo(video: VideoItem) {
  void playback.play(video).catch(() => ElMessage.error('无法获取视频播放地址'))
}
function playNext() {
  void playback.next(library.orderedVideos.value).catch(() => ElMessage.error('下一节播放失败'))
}
function playPrevious() {
  void playback.previous(library.orderedVideos.value).catch(() => ElMessage.error('上一节播放失败'))
}
function ignoreCancelOrReport(error: unknown) {
  if (error === 'cancel' || error === 'close') return
  ElMessage.error('操作失败，请检查网络或视频数据状态')
}
async function addFolder() {
  try {
    const { value } = await ElMessageBox.prompt('目录名称', '新建章节 / 目录', {
      inputPattern: /\S+/, inputErrorMessage: '请输入目录名称',
    })
    await library.addFolder(value)
    ElMessage.success('目录创建成功')
  } catch (error) { ignoreCancelOrReport(error) }
}
async function renameFolder(folder: VideoFolder) {
  try {
    const { value } = await ElMessageBox.prompt('目录名称', '重命名目录', {
      inputValue: folder.name, inputPattern: /\S+/, inputErrorMessage: '请输入目录名称',
    })
    await library.editFolder(folder.id, value)
    ElMessage.success('目录已重命名')
  } catch (error) { ignoreCancelOrReport(error) }
}
async function removeFolder(folder: VideoFolder) {
  try {
    await ElMessageBox.confirm('只能删除没有视频与子目录的空目录，确定删除吗？', '删除目录', {
      type: 'warning',
    })
    if (library.selectedFolderId.value === folder.id) playback.stop()
    await library.removeFolder(folder.id)
    ElMessage.success('空目录已删除')
  } catch (error) { ignoreCancelOrReport(error) }
}
async function editVideo(video: VideoItem) {
  try {
    const { value } = await ElMessageBox.prompt('视频名称', '编辑视频', {
      inputValue: video.title, inputPattern: /\S+/, inputErrorMessage: '请输入视频名称',
    })
    await library.editVideo(video.id, value, video.folderId)
    if (playback.playing.value?.id === video.id) playback.playing.value.title = value
    ElMessage.success('视频标题已更新')
  } catch (error) { ignoreCancelOrReport(error) }
}
async function removeVideo(video: VideoItem) {
  try {
    await ElMessageBox.confirm('视频文件将从服务器永久删除且无法恢复，是否继续？', '删除视频', {
      type: 'warning',
    })
    if (playback.playing.value?.id === video.id) playback.stop()
    await library.removeVideo(video.id)
    await uploads.refreshUsage()
    ElMessage.success('视频已删除')
  } catch (error) { ignoreCancelOrReport(error) }
}
async function uploadFile(file: File) {
  try {
    const video = await uploads.upload(file, library.selectedFolderId.value)
    await library.loadVideos()
    uploadOpen.value = false
    ElMessage.success('视频上传成功：' + video.title)
  } catch (error) {
    ElMessage.error(error instanceof Error && error.message
      ? error.message : '上传失败，重新选择同一 MP4 文件可继续上传')
  }
}
</script>

<template>
  <AppLayout>
    <div class="video-study-page">
      <VideoHeader :folder-title="library.folderTitle.value"
        :total="library.videos.value.length"
        @manage="managerOpen = true" @upload="uploadOpen = true" />

      <div class="video-study-layout">
        <VideoPlayer ref="playerRef" class="video-player-area"
          :video="playback.playing.value" :src="playback.playbackUrl.value"
          :speed="playback.speed.value" :volume="playback.volume.value"
          :loading="playback.loadingPlaybackId.value !== null"
          @speed-change="playback.changeSpeed" @volume-change="value => playback.volume.value = value"
          @progress="playback.onProgress" @pause="playback.onPause"
          @ended="playNext" />

        <VideoStudyInfo class="video-info-area" :video="playback.playing.value"
          :folder-title="library.folderTitle.value"
          :progress-percent="playback.progressPercent.value"
          :has-next="hasNext" :has-previous="hasPrevious"
          @next="playNext" @previous="playPrevious" />

        <VideoPlaylist class="video-playlist-area" :folders="library.flatFolders.value"
          :videos="library.orderedVideos.value"
          :current-folder-id="library.selectedFolderId.value"
          :playing-video-id="playback.playing.value?.id ?? null"
          :loading="library.loading.value"
          @select-folder="changeFolder" @select-video="changeVideo" />

        <VideoStudyTabs class="video-tabs-area"
          :video="playback.playing.value" :folder-title="library.folderTitle.value" />
      </div>

      <VideoLibraryManager v-model="managerOpen"
        :folders="library.flatFolders.value" :videos="library.orderedVideos.value"
        :current-folder-id="library.selectedFolderId.value"
        :usage="uploads.usage.value" :usage-percent="uploads.usagePercent.value"
        @select-folder="changeFolder"
        @create-folder="addFolder" @rename-folder="renameFolder" @delete-folder="removeFolder"
        @edit-video="editVideo" @delete-video="removeVideo" @upload="uploadOpen = true" />

      <VideoUploadDialog v-model="uploadOpen"
        :uploading="uploads.uploading.value" :progress="uploads.uploadPercent.value"
        :file-name="uploads.fileName.value" :folder-title="library.folderTitle.value"
        @upload="uploadFile" />
    </div>
  </AppLayout>
</template>

<style scoped>
.video-study-page{width:100%;max-width:1450px;margin:0 auto;padding-bottom:24px}
.video-study-layout{display:grid;grid-template-columns:minmax(0,1fr) 308px;
  grid-template-areas:"player playlist" "info playlist" "tabs playlist";
  column-gap:18px;row-gap:0;align-items:start}
.video-player-area{grid-area:player;min-width:0}
.video-info-area{grid-area:info;min-width:0}
.video-playlist-area{grid-area:playlist;min-width:0;position:sticky;top:16px}
.video-tabs-area{grid-area:tabs;min-width:0}
@media(max-width:1100px){
  .video-study-layout{grid-template-columns:minmax(0,1fr);
    grid-template-areas:"player" "info" "playlist" "tabs";row-gap:16px}
  .video-playlist-area{position:static}
}
@media(max-width:620px){.video-study-layout{row-gap:12px}.video-study-page{padding-bottom:16px}}
</style>
