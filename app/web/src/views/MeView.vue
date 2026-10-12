<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight, Bell, Collection, Document, InfoFilled, Lock, Setting, User, Cpu, Monitor, Tools,
} from '@element-plus/icons-vue'
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { createInvitation } from '@/api/auth'
import { disconnectCurrentDevice } from '@/api/notifications'

const auth = useAuthStore()
const router = useRouter()
const signingOut = ref(false)
const inviting = ref(false)
const menu = [
  { label: 'AI 模型与接口', hint: '配置六大服务商、API Key 与默认模型', icon: Cpu, to: '/me/ai-settings' },
  { label: '消息中心', hint: '提醒规则、站内消息及设备推送', icon: Bell, to: '/notifications' },
  { label: '设置', hint: '管理应用入口、消息和账号选项', icon: Setting, to: '/me/settings' },
  { label: '使用说明书', hint: '查看页面入口与常见操作', icon: Document, to: '/me/guide' },
  { label: '关于 Matrix PRP', hint: '项目说明与开发状态', icon: InfoFilled, to: '/me/about' },
]
async function inviteFriend() {
  if (inviting.value) return
  inviting.value = true
  try {
    const invitation = await createInvitation()
    await ElMessageBox.alert('邀请码：' + invitation.code + '（7 天有效，仅限一次注册）', '邀请朋友')
  } catch { ElMessage.error('生成邀请码失败') }
  finally { inviting.value = false }
}
async function logout() {
  if (signingOut.value) return
  try { await ElMessageBox.confirm('确定退出当前账号吗？', '退出登录', { type: 'warning' }) }
  catch { return }
  signingOut.value = true
  try {
    try { await disconnectCurrentDevice() }
    catch { ElMessage.warning('当前设备推送解绑失败，请在消息中心检查') }
    auth.logout()
    await router.replace('/login')
  } finally { signingOut.value = false }
}
</script>

<template>
  <AppLayout>
    <div class="prp-me-page">
      <header class="prp-section-header"><div><p class="eyebrow">MY SPACE</p><h1>我的</h1>
        <p>个人资料、消息通知、设置与帮助。</p></div></header>
      <section class="prp-profile-card">
        <span class="prp-profile-avatar"><el-icon><User /></el-icon></span>
        <div class="prp-profile-copy"><h2>{{ auth.user?.displayName || '我的空间' }}</h2>
          <p>{{ auth.user?.username || '已登录用户' }}</p>
          <span class="prp-profile-role"><el-icon><Lock /></el-icon>
            {{ auth.user?.administrator ? '管理员' : '个人用户' }}</span></div>
      </section>
      <section class="prp-me-menu" aria-label="个人功能">
        <RouterLink v-for="item in menu" :key="item.to" :to="item.to" class="prp-me-menu-item">
          <span class="prp-me-menu-icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="prp-me-menu-text"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
          <el-icon class="prp-me-menu-arrow"><ArrowRight /></el-icon>
        </RouterLink>
      </section>
      <section v-if="auth.user?.administrator" class="prp-me-admin">
        <span><el-icon><Collection /></el-icon> 管理员工具</span>
        <RouterLink to="/me/agent-tasks" class="prp-inline-link"><el-icon><Monitor /></el-icon> OpenClaw 任务工作台</RouterLink>
        <RouterLink to="/me/codex-jobs" class="prp-inline-link"><el-icon><Tools /></el-icon> Codex 开发任务</RouterLink>
        <el-button :loading="inviting" @click="inviteFriend">生成好友邀请码</el-button>
      </section>
      <el-button class="prp-sign-out" plain :loading="signingOut" @click="logout">退出登录</el-button>
    </div>
  </AppLayout>
</template>
