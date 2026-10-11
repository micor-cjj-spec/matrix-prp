<script setup lang="ts">
import { Bell, CollectionTag, DataAnalysis, Document, EditPen, Food, Menu, Money, Notebook, Tickets, VideoCamera } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createInvitation } from '@/api/auth'
import { disconnectCurrentDevice } from '@/api/notifications'
import { computed, ref } from 'vue'
import type { Component } from 'vue'
import { features } from '@/generated/features'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const inviting = ref(false)

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

const iconByCode: Record<string, Component> = {
  dashboard: DataAnalysis,
  records: Document,
  tasks: Tickets,
  finance: Money,
  wellness: Food,
  reviews: EditPen,
  tags: CollectionTag,
  knowledge: Notebook,
  videos: VideoCamera,
  notifications: Bell,
}

// Name, route, order and role visibility are sourced from the registry.
const navItems = computed(() => features
  .filter(feature => feature.enabled && feature.visibleInNav
    && (feature.visibility !== 'admin' || authStore.user?.administrator))
  .sort((a, b) => a.sortOrder - b.sortOrder)
  .map(feature => ({
    to: feature.webRoute,
    label: feature.name,
    icon: iconByCode[feature.code] ?? Menu,
  })))

async function logout() {
  try { await disconnectCurrentDevice() }
  catch { ElMessage.warning('当前设备推送解绑失败，请在通知中心移除设备或关闭系统通知') }
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <main class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">M</div>
        <div>
          <strong>Matrix PRP</strong>
          <span>个人资源管理平台</span>
        </div>
      </div>

      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.to" class="nav-item" :to="item.to">
          <el-icon><component :is="item.icon" /></el-icon>
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <span>{{ authStore.user?.displayName || 'Matrix PRP' }}</span>
        <el-button v-if="authStore.user?.administrator" size="small" :loading="inviting" @click="inviteFriend">邀请朋友</el-button>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </aside>

    <section class="workspace">
      <slot />
    </section>
  </main>
</template>


