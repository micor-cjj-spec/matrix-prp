import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/learning',
      name: 'learning',
      component: () => import('@/views/LearningView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/life',
      name: 'life',
      component: () => import('@/views/LifeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/records',
      name: 'records',
      component: () => import('@/views/RecordsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('@/views/TasksView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/finance',
      name: 'finance',
      component: () => import('@/views/FinanceView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/wellness',
      name: 'wellness',
      component: () => import('@/views/WellnessView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/reviews',
      name: 'reviews',
      component: () => import('@/views/ReviewsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/tags',
      name: 'tags',
      component: () => import('@/views/TagsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('@/views/KnowledgeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/videos',
      name: 'videos',
      component: () => import('@/views/VideosView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/views/NotificationsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/practice',
      name: 'practice',
      component: () => import('@/views/PracticeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/apps',
      name: 'apps',
      component: () => import('@/views/AppsView.vue'),
      meta: { requiresAuth: true, title: '应用中心' },
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true, title: 'PRP 助手' },
    },
    {
      path: '/me',
      name: 'me',
      component: () => import('@/views/MeView.vue'),
      meta: { requiresAuth: true, title: '我的' },
    },
    {
      path: '/me/ai-settings',
      name: 'my-ai-settings',
      component: () => import('@/views/AiSettingsView.vue'),
      meta: { requiresAuth: true, title: 'AI 模型与接口' },
    },
    {
      path: '/me/agent-tasks',
      name: 'my-agent-tasks',
      component: () => import('@/views/AgentTasksView.vue'),
      meta: { requiresAuth: true, adminOnly: true, title: 'OpenClaw 任务工作台' },
    },
    {
      path: '/me/codex-jobs',
      name: 'my-codex-jobs',
      component: () => import('@/views/CodexJobsView.vue'),
      meta: { requiresAuth: true, adminOnly: true, title: 'Codex 开发任务' },
    },
    {
      path: '/me/settings',
      name: 'my-settings',
      component: () => import('@/views/MeDetailView.vue'),
      props: { section: 'settings' },
      meta: { requiresAuth: true, title: '设置' },
    },
    {
      path: '/me/guide',
      name: 'my-guide',
      component: () => import('@/views/MeDetailView.vue'),
      props: { section: 'guide' },
      meta: { requiresAuth: true, title: '使用说明书' },
    },
    {
      path: '/me/about',
      name: 'my-about',
      component: () => import('@/views/MeDetailView.vue'),
      props: { section: 'about' },
      meta: { requiresAuth: true, title: '关于' },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.adminOnly && !authStore.user?.administrator) {
    return { name: 'me' }
  }
  if (to.name === 'login' && authStore.isAuthenticated) {
    return { name: 'dashboard' }
  }
  return true
})

export default router

