<script setup lang="ts">
import { CollectionTag, DataAnalysis, Document, EditPen, Money, Notebook, Tickets } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

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
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </aside>

    <section class="workspace">
      <slot />
    </section>
  </main>
</template>
