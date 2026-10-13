<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, ChatDotRound, DataAnalysis, Grid, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { domains, features } from '@/generated/features'

const route = useRoute()
const auth = useAuthStore()

// On iOS, a textarea can retain focus after the software keyboard has closed.
// Measure the actual visual viewport rather than using :focus to hide tabs.
const keyboardVisible = ref(false)
function updateKeyboardVisibility() {
  const viewport = window.visualViewport
  keyboardVisible.value = Boolean(viewport && window.innerHeight - viewport.height - viewport.offsetTop > 150)
}
function prepareMobileNavigation() {
  const active = document.activeElement
  if (active instanceof HTMLElement && active.matches('input, textarea, select, [contenteditable="true"]')) {
    active.blur()
  }
}
onMounted(() => {
  updateKeyboardVisibility()
  window.visualViewport?.addEventListener('resize', updateKeyboardVisibility)
  window.visualViewport?.addEventListener('scroll', updateKeyboardVisibility)
  window.addEventListener('resize', updateKeyboardVisibility)
})
onBeforeUnmount(() => {
  window.visualViewport?.removeEventListener('resize', updateKeyboardVisibility)
  window.visualViewport?.removeEventListener('scroll', updateKeyboardVisibility)
  window.removeEventListener('resize', updateKeyboardVisibility)
})
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
  if (typeof routeTitle === 'string') return routeTitle
  const currentFeature = features.find(item => item.webRoute === route.path)
  const currentDomain = domains.find(item => item.webRoute === route.path)
  return currentFeature?.name ?? currentDomain?.name
    ?? mainNav.find(item => item.code === activeMain.value)?.label ?? '应用'
})
</script>

<template>
  <main class="app-shell prp-shell" :class="{ 'prp-shell-chat': activeMain === 'chat', 'prp-keyboard-open': activeMain === 'chat' && keyboardVisible }">
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

    <div class="workspace prp-workspace" :class="{ 'prp-workspace-chat': activeMain === 'chat' }">
      <div v-if="activeMain !== 'chat'" class="prp-topbar">
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
      <section class="prp-page-content" :class="{ 'prp-page-chat': activeMain === 'chat' }"><slot /></section>
    </div>
    <nav class="prp-mobile-tabs" aria-label="手机主要导航">
      <RouterLink v-for="item in mainNav" :key="item.code" :to="item.to"
        class="prp-mobile-tab" :class="{ 'is-active': activeMain === item.code }" @pointerdown="prepareMobileNavigation"
        :aria-current="route.path === item.to ? 'page' : undefined">
        <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </main>
</template>
