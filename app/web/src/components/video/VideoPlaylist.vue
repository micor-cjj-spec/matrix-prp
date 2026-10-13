<script setup lang="ts">
import { computed, ref } from 'vue'
import { Collection, Search } from '@element-plus/icons-vue'
import type { VideoFolder, VideoItem } from '@/api/video'
import { videoProgressPercent } from '@/utils/videoStudy'
const props = defineProps<{
  folders: { folder: VideoFolder; depth: number }[]
  videos: VideoItem[]
  currentFolderId: number | null
  playingVideoId: number | null
  loading: boolean
}>()
const emit = defineEmits<{ 'select-folder': [id: number | null]; 'select-video': [video: VideoItem] }>()
const search = ref('')
const showAllFolders = ref(true)
const filteredVideos = computed(() => props.videos.filter(item =>
  item.title.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
</script>

<template>
  <aside class="study-playlist" aria-label="课程目录和视频选集">
    <header class="playlist-heading">
      <div><strong>课程目录</strong><small>{{ videos.length }} 节 · 选集</small></div>
      <el-button :icon="Collection" size="small" circle text aria-label="展开或收起目录"
        @click="showAllFolders = !showAllFolders" />
    </header>
    <div v-show="showAllFolders" class="folder-chooser">
      <button type="button" class="course-folder" :class="{ 'is-selected': currentFolderId === null }"
        @click="emit('select-folder', null)">全部视频</button>
      <button v-for="entry in folders" :key="entry.folder.id" type="button"
        class="course-folder" :class="{ 'is-selected': entry.folder.id === currentFolderId }"
        :style="{ paddingLeft: (12 + entry.depth * 15) + 'px' }"
        @click="emit('select-folder', entry.folder.id)">
        <span class="course-folder-icon">▸</span>{{ entry.folder.name }}
      </button>
    </div>
    <div class="playlist-search">
      <el-input v-model="search" :prefix-icon="Search" size="small" clearable placeholder="查找本目录视频" aria-label="查找视频" />
    </div>
    <div class="playlist-items" :aria-busy="loading">
      <p v-if="loading" class="playlist-empty">正在加载选集…</p>
      <p v-else-if="filteredVideos.length === 0" class="playlist-empty">当前目录暂无匹配视频</p>
      <button v-for="(video, index) in filteredVideos" :key="video.id" type="button"
        class="playlist-item" :class="{ 'is-playing': playingVideoId === video.id }"
        :aria-current="playingVideoId === video.id ? 'true' : undefined"
        @click="emit('select-video', video)">
        <span class="episode-index">{{ String(index + 1).padStart(2, '0') }}</span>
        <span class="episode-body">
          <span class="episode-title">{{ video.title }}</span>
          <span class="episode-detail">
            {{ (video.sizeBytes / 1048576).toFixed(1) }} MB
            <template v-if="videoProgressPercent(video) !== null"> · 已看 {{ videoProgressPercent(video) }}%</template>
            <template v-else-if="video.positionSeconds > 0"> · 已续播 {{ Math.floor(video.positionSeconds / 60) }} 分钟</template>
          </span>
          <span v-if="videoProgressPercent(video) !== null" class="episode-progress-track">
            <span :style="{ width: videoProgressPercent(video) + '%' }" />
          </span>
        </span>
        <span v-if="playingVideoId === video.id" class="playing-indicator">▶</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.study-playlist{display:flex;flex-direction:column;min-width:0;background:#fff;border:1px solid #e8edf5;border-radius:13px;overflow:hidden;box-shadow:0 6px 18px rgba(27,46,81,.03)}
.playlist-heading{display:flex;align-items:center;justify-content:space-between;padding:17px 17px 12px}
.playlist-heading>div{display:flex;flex-direction:column;gap:5px}.playlist-heading strong{font-size:15px;color:#192d4b}
.playlist-heading small{font-size:11px;color:#95a3b7}
.folder-chooser{padding:0 9px 12px;max-height:190px;overflow:auto;border-bottom:1px solid #eef1f6}
.course-folder{display:flex;align-items:center;gap:7px;width:100%;text-align:left;background:transparent;border:0;border-radius:8px;min-height:35px;padding:7px 12px;color:#61728d;font-size:12px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.course-folder:hover,.course-folder.is-selected{color:#2267db;background:#edf4ff;font-weight:600}
.course-folder-icon{font-size:10px;color:#96aac6}
.playlist-search{padding:13px 13px 8px}
.playlist-items{min-height:120px;max-height:510px;overflow:auto;padding:4px 8px 12px}
.playlist-empty{padding:16px 12px;text-align:center;color:#9ba9b9;font-size:12px}
.playlist-item{width:100%;display:flex;align-items:flex-start;gap:10px;text-align:left;border:0;background:#fff;border-radius:9px;padding:13px 10px;color:#34465f;cursor:pointer}
.playlist-item:hover{background:#f6f9fe}.playlist-item.is-playing{background:#edf4ff}
.episode-index{font-size:12px;color:#92a2b9;padding-top:2px;font-variant-numeric:tabular-nums}
.episode-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
.episode-title{font-size:13px;line-height:1.5;word-break:break-word;font-weight:550}
.is-playing .episode-title,.playing-indicator{color:#2563eb;font-weight:700}
.episode-detail{font-size:11px;color:#9ba9b9}.episode-progress-track{height:3px;border-radius:4px;background:#e1eaf7;overflow:hidden}
.episode-progress-track>span{display:block;height:100%;background:#4a8bee;border-radius:4px}
.playing-indicator{font-size:10px;margin-top:3px}
@media(max-width:1100px){.playlist-items{max-height:300px}}
</style>
