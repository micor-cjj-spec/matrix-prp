<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, ChatDotRound, DataAnalysis, Grid, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()
const mainNav = [
  { code: 'home', label: '首页', to: '/', icon: DataAnalysis },
  { code: 'apps', label: '应用', to: '/apps', icon: Grid },
  { code: 'chat', label: '聊天', to: '/chat', icon: ChatDotRound },
  { code: 'me', label: '我的', to: '/me', icon: User },
] as const

const activeMain = computed(() => {
  const path = route.path
  if (path === '/') return 'home'
  if (path === '/chat' || path.startsWith('/chat/')) return 'chat'
  if (path === '/me' || path.startsWith('/me/') || path === '/notifications') return 'me'
  return 'apps'
})
const currentTitle = computed(() => {
  const routeTitle = route.meta.title
  return typeof routeTitle === 'string'
    ? routeTitle
    : mainNav.find(item => item.code === activeMain.value)?.label ?? '应用'
})
</script>

<template>
  <main class="app-shell prp-shell">
    <aside class="sidebar prp-sidebar" aria-label="主导航">
      <RouterLink to="/" class="brand prp-brand">
        <span class="brand-mark">M</span>
        <span class="brand-copy"><strong>Matrix PRP</strong><small>个人成长与生活空间</small></span>
      </RouterLink>
      <p class="nav-caption">个人工作空间</p>
      <nav class="nav-list prp-main-nav" aria-label="主要空间">
        <RouterLink v-for="item in mainNav" :key="item.code" :to="item.to"
          class="nav-item prp-nav-link" :class="{ 'is-active': activeMain === item.code }"
          :aria-current="route.path === item.to ? 'page' : undefined">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer prp-sidebar-footer">
        <RouterLink to="/me" class="prp-user-card">
          <span class="prp-user-avatar">{{ (auth.user?.displayName || '我').slice(0, 1) }}</span>
          <span class="prp-user-name"><strong>{{ auth.user?.displayName || '我的空间' }}</strong>
            <small>{{ auth.user?.administrator ? '管理员' : '个人用户' }}</small></span>
        </RouterLink>
      </div>
    </aside>

    <div class="workspace prp-workspace">
      <div class="prp-topbar">
        <div class="prp-topbar-title"><span class="prp-mobile-mark">M</span><span>{{ currentTitle }}</span></div>
        <div class="prp-topbar-actions">
          <RouterLink to="/notifications" class="prp-icon-link" aria-label="消息与提醒">
            <el-icon><Bell /></el-icon>
          </RouterLink>
          <RouterLink to="/me" class="prp-user-card prp-topbar-user" aria-label="个人中心">
            <span class="prp-topbar-avatar">{{ (auth.user?.displayName || '我').slice(0, 1) }}</span>
          </RouterLink>
        </div>
      </div>
      <section class="prp-page-content"><slot /></section>
    </div>
    <nav class="prp-mobile-tabs" aria-label="手机主要导航">
      <RouterLink v-for="item in mainNav" :key="item.code" :to="item.to"
        class="prp-mobile-tab" :class="{ 'is-active': activeMain === item.code }"
        :aria-current="route.path === item.to ? 'page' : undefined">
        <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </main>
</template>
