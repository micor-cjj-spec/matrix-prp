<script setup lang="ts">
import type { VideoFolder, VideoItem, StorageUsage } from '@/api/video'
const visible = defineModel<boolean>({ default: false })
defineProps<{
  folders: { folder: VideoFolder; depth: number }[]
  videos: VideoItem[]
  currentFolderId: number | null
  usage: StorageUsage | null
  usagePercent: number
}>()
const emit = defineEmits<{
  'select-folder': [id: number | null]
  'create-folder': []
  'rename-folder': [folder: VideoFolder]
  'delete-folder': [folder: VideoFolder]
  'edit-video': [video: VideoItem]
  'delete-video': [video: VideoItem]
  upload: []
}>()
function selectFolder(id: number | null) {
  emit('select-folder', id)
  visible.value = false
}
function size(bytes: number) {
  return bytes >= 1073741824 ? (bytes / 1073741824).toFixed(2) + ' GiB'
    : (bytes / 1048576).toFixed(1) + ' MiB'
}
</script>
<template>
  <el-drawer v-model="visible" title="课程与视频管理" size="min(92vw, 460px)" append-to-body>
    <div class="manager-panel">
      <div class="manager-actions">
        <el-button type="primary" plain @click="emit('create-folder')">+ 新建目录</el-button>
        <el-button @click="emit('upload')">上传视频</el-button>
      </div>
      <h3>目录结构</h3>
      <button type="button" class="manage-folder" :class="{ chosen: currentFolderId === null }"
        @click="selectFolder(null)">全部视频</button>
      <div v-for="entry in folders" :key="entry.folder.id" class="manage-folder-row"
        :style="{ paddingLeft: (entry.depth * 16) + 'px' }">
        <button type="button" class="manage-folder"
          :class="{ chosen: currentFolderId === entry.folder.id }"
          @click="selectFolder(entry.folder.id)">📁 {{ entry.folder.name }}</button>
        <el-dropdown trigger="click">
          <el-button size="small" text>⋯</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="emit('rename-folder', entry.folder)">重命名</el-dropdown-item>
              <el-dropdown-item @click="emit('delete-folder', entry.folder)">删除空目录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <h3>当前目录视频</h3>
      <p v-if="!videos.length" class="empty-hint">当前目录暂无视频</p>
      <div v-for="video in videos" :key="video.id" class="manage-video">
        <span class="manage-video-title">{{ video.title }}</span>
        <el-button size="small" text @click="emit('edit-video', video)">编辑</el-button>
        <el-button size="small" text type="danger" @click="emit('delete-video', video)">删除</el-button>
      </div>
      <template v-if="usage">
        <h3>我的视频空间</h3>
        <p class="usage-label">{{ size(usage.bytesUsed) }} / {{ size(usage.quotaBytes) }} · {{ usage.fileCount }} 个视频</p>
        <el-progress :percentage="usagePercent" :show-text="false" />
      </template>
    </div>
  </el-drawer>
</template>
<style scoped>
.manager-panel{display:grid;gap:9px}.manager-actions{display:flex;gap:8px;margin-bottom:10px}
.manager-panel h3{font-size:14px;color:#34445f;margin:16px 0 6px;border-top:1px solid #e7edf6;padding-top:14px}
.manage-folder-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.manage-folder{border:0;background:none;text-align:left;cursor:pointer;padding:8px 10px;font-size:13px;color:#5e6e88;border-radius:7px;flex:1;min-width:0}
.manage-folder:hover,.manage-folder.chosen{background:#eaf2ff;color:#2563eb}
.manage-video{display:flex;align-items:center;gap:4px;padding:6px 0;border-bottom:1px solid #f1f4f9}
.manage-video-title{font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.empty-hint,.usage-label{font-size:12px;color:#8694a9}
</style>
