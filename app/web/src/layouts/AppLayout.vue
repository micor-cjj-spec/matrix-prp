<script setup lang="ts">
import { CollectionTag, DataAnalysis, Document, EditPen, Money, Notebook, Tickets } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createInvitation } from '@/api/auth'
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
  { to: '/', label: 'Dashboard', icon: DataAnalysis },
  { to: '/records', label: 'Records', icon: Document },
  { to: '/tasks', label: 'Tasks', icon: Tickets },
  { to: '/finance', label: 'Finance', icon: Money },
  { to: '/reviews', label: 'Reviews', icon: EditPen },
  { to: '/tags', label: 'Tags', icon: CollectionTag },
  { to: '/knowledge', label: 'Knowledge', icon: Notebook },
]

function logout() {
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
          <span>Personal resource planning</span>
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
