<script setup lang="ts">
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import type { VideoItem } from '@/api/video'
defineProps<{
  video: VideoItem | null
  folderTitle: string
  progressPercent: number | null
  hasPrevious: boolean
  hasNext: boolean
}>()
defineEmits<{ previous: []; next: [] }>()
</script>
<template>
  <section class="study-info">
    <div class="study-info-copy">
      <span class="study-video-label">正在学习 · {{ folderTitle }}</span>
      <h2>{{ video?.title || '选择一节课程开始学习' }}</h2>
      <p v-if="video && progressPercent !== null">本节已观看 {{ progressPercent }}% · 观看进度自动保存至账户</p>
      <p v-else>视频进度会自动保存，支持稍后继续观看</p>
    </div>
    <div class="study-next-actions">
      <el-button :icon="ArrowLeft" :disabled="!video || !hasPrevious" @click="$emit('previous')">上一节</el-button>
      <el-button type="primary" :disabled="!video || !hasNext" @click="$emit('next')">
        下一节 <el-icon class="next-icon"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </section>
</template>
<style scoped>
.study-info{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:21px 4px 18px;flex-wrap:wrap}
.study-info-copy{min-width:0}.study-video-label{font-size:11px;font-weight:650;color:#517eb9}
.study-info h2{font-size:clamp(17px,1.8vw,22px);margin:6px 0;color:#1c2d48;font-weight:700;line-height:1.4}
.study-info p{margin:0;color:#90a0b5;font-size:12px}
.study-next-actions{display:flex;gap:8px;white-space:nowrap}.next-icon{margin-left:4px}
@media(max-width:620px){.study-info{padding:16px 0;}.study-next-actions{width:100%;justify-content:flex-end}}
</style>
