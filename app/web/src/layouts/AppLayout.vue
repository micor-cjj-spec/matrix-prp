<script setup lang="ts">
import { ChatDotRound, Bell, CollectionTag, DataAnalysis, Document, EditPen, Money, Notebook, Tickets, VideoCamera } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createInvitation } from '@/api/auth'
import { disconnectCurrentDevice } from '@/api/notifications'
import { ref } from 'vue'
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

const navItems = [
  { to: '/', label: '首页概览', icon: DataAnalysis },
  { to: '/records', label: '记录管理', icon: Document },
  { to: '/tasks', label: '任务计划', icon: Tickets },
  { to: '/finance', label: '财务管理', icon: Money },
  { to: '/reviews', label: '复盘中心', icon: EditPen },
  { to: '/tags', label: '标签管理', icon: CollectionTag },
  { to: '/knowledge', label: '知识库', icon: Notebook },
  { to: '/ai', label: 'Matrix AI', icon: ChatDotRound },
  { to: '/videos', label: '视频学习库', icon: VideoCamera },
  { to: '/notifications', label: '消息与提醒', icon: Bell },
]

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


