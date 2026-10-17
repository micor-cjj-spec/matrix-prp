<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/layouts/AppLayout.vue'
import { ArrowRight, Collection, Document, Notebook, Reading, VideoCamera, Headset } from '@element-plus/icons-vue'

const auth = useAuthStore()
const canOpenKnowledge = computed(() => Boolean(auth.user?.administrator))
</script>

<template>
  <AppLayout>
    <div class="domain-page domain-learning">
      <header class="domain-hero">
        <div class="domain-hero-icon"><el-icon><Reading /></el-icon></div>
        <div>
          <p class="eyebrow">LEARNING HUB · 学习空间</p>
          <h1>把每一次学习，变成看得见的成长</h1>
          <p>课程、练习与知识沉淀集中管理。先从你已经拥有的学习工具开始。</p>
        </div>
      </header>

      <div class="domain-section-heading">
        <div><h2>我的学习工具</h2><p>学习内容统一归类，不再挤在一级导航中。</p></div>
      </div>
      <div class="domain-tool-grid">
        <RouterLink class="domain-tool-card" to="/videos">
          <span class="tool-icon tool-blue"><el-icon><VideoCamera /></el-icon></span>
          <div><h3>视频课程</h3><p>课程目录、章节播放、倍速和学习进度</p><span class="tool-action">进入视频学习 <el-icon><ArrowRight /></el-icon></span></div>
        </RouterLink>
        <RouterLink class="domain-tool-card" to="/practice">
          <span class="tool-icon tool-violet"><el-icon><Collection /></el-icon></span>
          <div><h3>智能刷题</h3><p>多学科题库、题库导入、错题练习与 AI 辅助解答</p><span class="tool-action">进入智能刷题 <el-icon><ArrowRight /></el-icon></span></div>
        </RouterLink>
        <RouterLink class="domain-tool-card" to="/vocal">
          <span class="tool-icon tool-blue"><el-icon><Headset /></el-icon></span>
          <div><h3>声乐训练</h3><p>录音练声、音高观察、AI 教练与练习历史</p><span class="tool-action">进入声乐训练 <el-icon><ArrowRight /></el-icon></span></div>
        </RouterLink>
        <RouterLink class="domain-tool-card" to="/records">
          <span class="tool-icon tool-amber"><el-icon><Document /></el-icon></span>
          <div><h3>学习笔记与记录</h3><p>记录学习心得、内容摘要和进展</p><span class="tool-action">查看记录 <el-icon><ArrowRight /></el-icon></span></div>
        </RouterLink>
        <RouterLink v-if="canOpenKnowledge" class="domain-tool-card" to="/knowledge">
          <span class="tool-icon tool-green"><el-icon><Notebook /></el-icon></span>
          <div><h3>Markdown 知识库</h3><p>搜索和阅读服务器中的现有知识资料</p><span class="tool-action">打开知识库 <el-icon><ArrowRight /></el-icon></span></div>
        </RouterLink>
      </div>

      <section class="domain-help-panel">
        <h2>推荐的学习路径</h2>
        <p>看课程 → 做题练习 → 记录错题 → 回顾总结。AI 辅助出题与解答需要服务器配置 DeepSeek API。</p>
        <div class="domain-mini-links">
          <RouterLink to="/tasks">安排学习任务 <el-icon><ArrowRight /></el-icon></RouterLink>
          <RouterLink to="/reviews">查看学习复盘 <el-icon><ArrowRight /></el-icon></RouterLink>
        </div>
      </section>
    </div>
  </AppLayout>
</template>
