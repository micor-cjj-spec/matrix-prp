<script setup lang="ts">
const visible = defineModel<boolean>({ default: false })
defineProps<{ uploading: boolean; progress: number; fileName: string; folderTitle: string }>()
const emit = defineEmits<{ upload: [file: File] }>()
function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', file)
  input.value = ''
}
</script>
<template>
  <el-dialog v-model="visible" title="上传课程视频" width="min(92vw, 500px)" :close-on-click-modal="!uploading"
    :close-on-press-escape="!uploading" :show-close="!uploading">
    <p class="upload-hint">上传位置：{{ folderTitle }} · MP4 格式 · 单视频不超过 2 GiB</p>
    <label class="upload-drop" :class="{ 'is-busy': uploading }">
      <input type="file" accept=".mp4,video/mp4" :disabled="uploading" @change="pickFile" />
      <strong>选择 MP4 视频</strong>
      <span>支持分片上传，上传中断后可重新选择相同文件续传</span>
    </label>
    <div v-if="uploading" class="upload-status" role="status">
      <span>{{ fileName }}</span>
      <el-progress :percentage="progress" />
    </div>
    <template #footer>
      <el-button :disabled="uploading" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>
<style scoped>
.upload-hint{font-size:12px;color:#7a899d;margin:0 0 16px}
.upload-drop{display:flex;align-items:center;justify-content:center;gap:9px;flex-direction:column;min-height:160px;border:1px dashed #aac6ec;border-radius:12px;background:#f7faff;color:#3264aa;cursor:pointer}
.upload-drop input{display:none}.upload-drop strong{font-size:14px}.upload-drop span{font-size:12px;color:#8494ac;text-align:center;padding:0 12px}
.upload-drop.is-busy{opacity:.6;cursor:not-allowed}.upload-status{margin-top:18px;font-size:12px;color:#6d819d}
</style>
