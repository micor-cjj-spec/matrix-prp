<script setup lang="ts">
import AppLayout from '@/layouts/AppLayout.vue'
import { ArrowRight, Bell, Calendar, CollectionTag, Document, EditPen, Tickets } from '@element-plus/icons-vue'
</script>

<template>
  <AppLayout>
    <div class="domain-page domain-life">
      <header class="domain-hero">
        <div class="domain-hero-icon"><el-icon><Calendar /></el-icon></div>
        <div>
          <p class="eyebrow">LIFE HUB · 生活空间</p>
          <h1>把日常安排得更从容</h1>
          <p>任务、生活记录与周期复盘，让重要的事保持清晰。</p>
        </div>
      </header>
      <div class="domain-section-heading"><div><h2>日常管理</h2><p>由现有功能组合而成，可直接使用。</p></div></div>
      <div class="domain-tool-grid">
        <RouterLink class="domain-tool-card" to="/tasks"><span class="tool-icon tool-blue"><el-icon><Tickets /></el-icon></span><div><h3>任务与计划</h3><p>今日待办、截止日期、优先级</p><span class="tool-action">管理任务 <el-icon><ArrowRight /></el-icon></span></div></RouterLink>
        <RouterLink class="domain-tool-card" to="/records"><span class="tool-icon tool-amber"><el-icon><Document /></el-icon></span><div><h3>生活记录</h3><p>记录每天的小事与重要片段</p><span class="tool-action">添加记录 <el-icon><ArrowRight /></el-icon></span></div></RouterLink>
        <RouterLink class="domain-tool-card" to="/reviews"><span class="tool-icon tool-green"><el-icon><EditPen /></el-icon></span><div><h3>每周复盘</h3><p>总结收获、问题和下阶段目标</p><span class="tool-action">查看复盘 <el-icon><ArrowRight /></el-icon></span></div></RouterLink>
        <RouterLink class="domain-tool-card" to="/notifications"><span class="tool-icon tool-violet"><el-icon><Bell /></el-icon></span><div><h3>消息提醒</h3><p>为重要日程创建自定义提醒</p><span class="tool-action">设置提醒 <el-icon><ArrowRight /></el-icon></span></div></RouterLink>
      </div>
      <section class="domain-help-panel">
        <h2>整理你的生活资料</h2>
        <p>通过标签归类生活、学习或工作记录，日后更容易查找。</p>
        <div class="domain-mini-links"><RouterLink to="/tags">管理标签 <el-icon><CollectionTag /></el-icon></RouterLink></div>
      </section>
    </div>
  </AppLayout>
</template>
