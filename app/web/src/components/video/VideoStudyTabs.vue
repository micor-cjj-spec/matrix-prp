<script setup lang="ts">
import { ref } from 'vue'
import type { VideoItem } from '@/api/video'
defineProps<{ video: VideoItem | null; folderTitle: string }>()
const activeTab = ref('overview')
</script>

<template>
  <section class="study-tabs">
    <el-tabs v-model="activeTab" class="study-tabs-tabs">
      <el-tab-pane label="课程简介" name="overview">
        <div class="study-tab-body">
          <h3>本节内容</h3>
          <p v-if="video">当前视频：{{ video.title }} · 所属目录：{{ folderTitle }}。</p>
          <p v-else>选择视频后可以在这里查看本节信息。</p>
          <p>切换课程时自动保存进度，返回后可从原位置继续学习。</p>
        </div>
      </el-tab-pane>
      <el-tab-pane label="学习笔记" name="notes">
        <div class="study-tab-body">
          <h3>学习笔记</h3>
          <p>时间点笔记和视频跳转标记将在后续学习功能中提供，本次改版不创建未保存的假笔记。</p>
        </div>
      </el-tab-pane>
      <el-tab-pane label="章节练习" name="practice">
        <div class="study-tab-body">
          <h3>巩固所学</h3>
          <p>可前往现有刷题中心练习。视频与题库的章节关联将在后续版本接入。</p>
          <RouterLink to="/practice" class="study-link">进入刷题中心 →</RouterLink>
        </div>
      </el-tab-pane>
      <el-tab-pane label="AI 助手" name="ai">
        <div class="study-tab-body">
          <h3>PRP AI 助手</h3>
          <p>你可以使用现有 AI 聊天。自动读取视频字幕和基于视频内容的讲解尚未实现。</p>
          <RouterLink to="/chat" class="study-link">打开 PRP 助手 →</RouterLink>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<style scoped>
.study-tabs{border:1px solid #e8edf5;background:#fff;border-radius:13px;padding:9px 23px 22px;min-height:185px}
.study-tab-body h3{color:#223651;font-size:15px;margin:9px 0}
.study-tab-body p{font-size:13px;color:#75849b;line-height:1.8;margin:7px 0}
.study-link{display:inline-block;margin-top:9px;color:#2867e9;text-decoration:none;font-size:13px;font-weight:600}
.study-link:hover{text-decoration:underline}
@media(max-width:620px){.study-tabs{padding:6px 13px 15px}}
</style>
