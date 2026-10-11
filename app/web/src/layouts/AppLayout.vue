<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Bell, CollectionTag, DataAnalysis, Document, EditPen, Food, House,
  Menu, Money, Notebook, Reading, Tickets, VideoCamera
} from '@element-plus/icons-vue'
import { createInvitation } from '@/api/auth'
import { disconnectCurrentDevice } from '@/api/notifications'
import { features, domains } from '@/generated/features'
import { useAuthStore } from '@/stores/auth'

type NavItem = { code: string; label: string; to: string; icon: Component }
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const inviting = ref(false)
const signingOut = ref(false)

function featurePath(code: string): string {
  return features.find(item => item.code === code)?.webRoute ?? '/'
}
function domainPath(code: string): string {
  return domains.find(item => item.code === code && item.status === 'landing')?.webRoute ?? '/'
}

const mainNav: NavItem[] = [
  { code: 'dashboard', label: '首页', to: featurePath('dashboard'), icon: DataAnalysis },
  { code: 'learning', label: '学习', to: domainPath('learning'), icon: Reading },
  { code: 'wellness', label: '健康', to: featurePath('wellness'), icon: Food },
  { code: 'life', label: '生活', to: domainPath('life'), icon: House },
  { code: 'finance', label: '财务', to: featurePath('finance'), icon: Money },
]
const utilityIcons: Record<string, Component> = {
  tasks: Tickets, records: Document, reviews: EditPen, tags: CollectionTag,
  notifications: Bell,
}
const utilities = computed<NavItem[]>(() => features
  .filter(feature => feature.enabled && feature.visibleInNav
    && Object.prototype.hasOwnProperty.call(utilityIcons, feature.code)
    && (feature.visibility !== 'admin' || auth.user?.administrator))
  .sort((a, b) => a.sortOrder - b.sortOrder)
  .map(feature => ({ code: feature.code, label: feature.name,
    to: feature.webRoute, icon: utilityIcons[feature.code] ?? Menu })))

const learningLinks = computed<NavItem[]>(() => [
  { code: 'videos', label: '视频课程', to: featurePath('videos'), icon: VideoCamera },
  ...(auth.user?.administrator
    ? [{ code: 'knowledge', label: '知识库', to: featurePath('knowledge'), icon: Notebook }]
    : []),
])
const showLearningChildren = computed(() =>
  route.path === domainPath('learning') || learningLinks.value.some(item => item.to === route.path))
const activeMain = computed(() => {
  const path = route.path
  if (path === '/videos' || path === '/knowledge') return 'learning'
  if (path === '/records' || path === '/tasks' || path === '/reviews' || path === '/tags' || path === '/notifications') return 'life'
  return mainNav.find(item => item.to === path)?.code ?? 'dashboard'
})
const currentTitle = computed(() =>
  [...mainNav, ...utilities.value, ...learningLinks.value].find(item => item.to === route.path)?.label ?? '工作台')

async function inviteFriend() {
  inviting.value = true
  try {
    const invitation = await createInvitation()
    await ElMessageBox.alert('邀请码：' + invitation.code + '（7 天有效，仅限一次注册）', '邀请朋友')
  } catch {
    ElMessage.error('生成邀请码失败')
  } finally {
    inviting.value = false
  }
}
async function logout() {
  if (signingOut.value) return
  signingOut.value = true
  try {
    try { await disconnectCurrentDevice() }
    catch { ElMessage.warning('推送设备解绑失败，请在通知中心检查') }
    auth.logout()
    await router.push({ name: 'login' })
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <main class="app-shell prp-shell">
    <aside class="sidebar prp-sidebar" aria-label="主导航">
      <RouterLink to="/" class="brand prp-brand">
        <span class="brand-mark">M</span>
        <span class="brand-copy"><strong>Matrix PRP</strong><small>个人成长与生活空间</small></span>
      </RouterLink>
      <p class="nav-caption">主要空间</p>
      <nav class="nav-list prp-main-nav" aria-label="主要空间">
        <template v-for="item in mainNav" :key="item.code">
          <RouterLink :to="item.to" class="nav-item prp-nav-link"
            :class="{ 'is-active': activeMain === item.code }"
            :aria-current="route.path === item.to ? 'page' : undefined">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </RouterLink>
          <div v-if="item.code === 'learning' && showLearningChildren" class="prp-subnav" aria-label="学习工具">
            <RouterLink v-for="child in learningLinks" :key="child.code" :to="child.to"
              class="prp-subnav-link" active-class="is-active">
              <el-icon><component :is="child.icon" /></el-icon>{{ child.label }}
            </RouterLink>
            <span class="prp-subnav-upcoming">智能刷题 · 待接入</span>
          </div>
        </template>
      </nav>
      <p class="nav-caption nav-caption-tools">效率工具</p>
      <nav class="nav-list prp-utility-nav" aria-label="效率工具">
        <RouterLink v-for="item in utilities" :key="item.code" :to="item.to"
          class="nav-item prp-nav-link" active-class="is-active">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer prp-sidebar-footer">
        <span class="prp-user-avatar">{{ (auth.user?.displayName || '我').slice(0, 1) }}</span>
        <div class="prp-user-name"><strong>{{ auth.user?.displayName || '我的空间' }}</strong><small>{{ auth.user?.administrator ? '管理员' : '个人用户' }}</small></div>
        <el-button text size="small" :loading="signingOut" @click="logout">退出</el-button>
      </div>
    </aside>

    <div class="workspace prp-workspace">
      <div class="prp-topbar">
        <div class="prp-topbar-title"><span class="prp-mobile-mark">M</span><span>{{ currentTitle }}</span></div>
        <div class="prp-topbar-actions">
          <RouterLink to="/notifications" class="prp-icon-link" aria-label="消息与提醒"><el-icon><Bell /></el-icon></RouterLink>
          <el-button v-if="auth.user?.administrator" class="prp-invite-button" size="small" :loading="inviting" @click="inviteFriend">邀请朋友</el-button>
          <span class="prp-topbar-avatar">{{ (auth.user?.displayName || '我').slice(0, 1) }}</span>
          <el-button class="prp-mobile-exit" text size="small" :loading="signingOut" @click="logout">退出</el-button>
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
