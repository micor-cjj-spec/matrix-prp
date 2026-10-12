<script setup lang="ts">
import { ArrowLeft, ArrowRight, Bell, Collection, InfoFilled, Setting } from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'

defineProps<{ section: 'settings' | 'guide' | 'about' }>()
</script>

<template>
  <AppLayout>
    <div class="prp-me-detail">
      <RouterLink to="/me" class="prp-inline-link"><el-icon><ArrowLeft /></el-icon> 返回我的</RouterLink>
      <template v-if="section === 'settings'">
        <header class="prp-section-header"><div><p class="eyebrow">SETTINGS</p><h1>设置</h1>
          <p>管理现有应用的快捷入口、通知和账号。</p></div></header>
        <div class="prp-me-menu">
          <RouterLink to="/apps" class="prp-me-menu-item"><span class="prp-me-menu-icon"><el-icon><Collection /></el-icon></span>
            <span class="prp-me-menu-text"><strong>常用应用</strong><small>在应用中心收藏或取消收藏</small></span>
            <el-icon><ArrowRight /></el-icon></RouterLink>
          <RouterLink to="/notifications" class="prp-me-menu-item"><span class="prp-me-menu-icon"><el-icon><Bell /></el-icon></span>
            <span class="prp-me-menu-text"><strong>消息与推送</strong><small>管理已有提醒和设备订阅</small></span>
            <el-icon><ArrowRight /></el-icon></RouterLink>
        </div>
        <p class="prp-apps-note">本阶段仅整合已有设置入口；暂不提供尚无后端支持的账号修改和系统开关。</p>
      </template>
      <template v-else-if="section === 'guide'">
        <header class="prp-section-header"><div><p class="eyebrow">USER GUIDE</p><h1>使用说明书</h1>
          <p>开始使用 Matrix PRP 的四个主入口。</p></div></header>
        <div class="prp-detail-sheet">
          <h2>首页</h2><p>查看今日任务、健康摄入、学习和财务摘要，快速进入正在做的事。</p>
          <h2>应用</h2><p>搜索已有功能、按领域筛选和收藏常用应用。学习页提供视频、刷题等入口。</p>
          <h2>聊天</h2><p>统一 AI 入口正在接入；当前版本不提供真实对话服务。</p>
          <h2>我的</h2><p>访问消息提醒、偏好入口、账号信息和帮助。管理员可以生成好友邀请码。</p>
          <p>如需查看某个业务模块的详细规则，请参考仓库 app/docs/technical 下的相应模块文档。</p>
        </div>
      </template>
      <template v-else>
        <header class="prp-section-header"><div><p class="eyebrow">ABOUT</p><h1>关于 Matrix PRP</h1>
          <p>个人资源管理与成长平台。</p></div></header>
        <div class="prp-detail-sheet"><span class="prp-chat-emblem"><el-icon><InfoFilled /></el-icon></span>
          <h2>一个不断扩展的个人空间</h2>
          <p>Matrix PRP 基于 Spring Boot、Vue 3 和 MySQL，涵盖学习、健康、任务、财务与个人记录。</p>
          <p>本次升级将首页、应用、聊天、我的确定为固定导航。AI 聊天能力仍需后续服务集成。</p>
          <p>版本和发布进度以项目 GitHub 的 main 分支及发布记录为准。</p>
        </div>
      </template>
    </div>
  </AppLayout>
</template>
