<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const isRegister = ref(false)
const errorMessage = ref('')

const form = reactive({
  username: '',
  password: '',
  displayName: '',
  invitationCode: '',
})

async function submitLogin() {
  errorMessage.value = ''
  loading.value = true
  try {
    if (isRegister.value) {
      await authStore.registerWithInvitation(form)
    } else {
      await authStore.loginWithPassword(form.username, form.password)
    }
    await authStore.loadCurrentUser()
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch {
    errorMessage.value = isRegister.value ? '注册失败，请检查邀请码、用户名和密码' : '账号或密码不正确'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="brand login-brand">
        <div class="brand-mark">M</div>
        <div>
          <strong>Matrix PRP</strong>
          <span>个人资源管理平台</span>
        </div>
      </div>

      <div class="login-copy">
        <p class="eyebrow">个人空间</p>
        <h1>进入个人资源管理平台</h1>
        <p>使用个人账号登录；新朋友需要邀请码才能注册。</p>
      </div>

      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />

      <el-form class="login-form" label-position="top" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>

        <template v-if="isRegister">
          <el-form-item label="显示名称"><el-input v-model="form.displayName" autocomplete="nickname" /></el-form-item>
          <el-form-item label="邀请码"><el-input v-model="form.invitationCode" autocomplete="off" /></el-form-item>
          <p>密码至少 12 位；用户名只能包含字母、数字和下划线。</p>
        </template>
        <el-button type="primary" :loading="loading" @click="submitLogin">{{ isRegister ? '注册并登录' : '登录' }}</el-button>
        <el-button text @click="isRegister = !isRegister">{{ isRegister ? '已有账号？返回登录' : '收到邀请码？注册账号' }}</el-button>
      </el-form>
    </section>
  </main>
</template>
