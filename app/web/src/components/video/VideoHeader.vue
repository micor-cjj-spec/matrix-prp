<script setup lang="ts">
import { ArrowLeft, FolderOpened, Upload } from '@element-plus/icons-vue'
defineProps<{ folderTitle: string; total: number }>()
defineEmits<{ manage: []; upload: [] }>()
</script>

<template>
  <header class="study-header">
    <div class="study-header-copy">
      <RouterLink to="/learning" class="study-back"><el-icon><ArrowLeft /></el-icon> 返回学习中心</RouterLink>
      <h1>视频学习 <span class="study-heading-dot">·</span> <span>{{ folderTitle }}</span></h1>
      <p>沉浸观看 · 自动同步学习进度 · 共 {{ total }} 节视频</p>
    </div>
    <div class="study-header-actions">
      <el-button :icon="FolderOpened" @click="$emit('manage')">课程管理</el-button>
      <el-button type="primary" :icon="Upload" @click="$emit('upload')">上传视频</el-button>
    </div>
  </header>
</template>

<style scoped>
.study-header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 22px;flex-wrap:wrap}
.study-header-copy{min-width:0}.study-back{display:inline-flex;align-items:center;gap:5px;text-decoration:none;color:#71809a;font-size:12px;margin-bottom:11px}
.study-back:hover{color:#2865e9}h1{font-size:clamp(21px,2vw,29px);line-height:1.25;margin:0 0 7px;color:#14233e;letter-spacing:-.5px}
h1 span:last-child{color:#526c9a;font-size:.72em;font-weight:600}.study-heading-dot{color:#bcc8dc}
p{margin:0;color:#8694a8;font-size:12px}.study-header-actions{display:flex;align-items:center;gap:8px}
@media(max-width:620px){.study-header{gap:12px}.study-header-actions{width:100%;justify-content:flex-end}}
</style>
