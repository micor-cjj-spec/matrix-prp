<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const errorMessage = ref('')

const form = reactive({
  username: 'admin',
  password: 'matrix-prp',
})

async function submitLogin() {
  errorMessage.value = ''
  loading.value = true
  try {
    await authStore.loginWithPassword(form.username, form.password)
    await authStore.loadCurrentUser()
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch {
    errorMessage.value = '账号或密码不正确，开发默认账号：admin / matrix-prp'
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
          <span>Personal resource planning</span>
        </div>
      </div>

      <div class="login-copy">
        <p class="eyebrow">Phase 1</p>
        <h1>进入个人资源管理平台</h1>
        <p>先用开发账号登录，进入 Dashboard、记录、任务、财务和知识库。</p>
      </div>

      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />

      <el-form class="login-form" label-position="top" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="submitLogin">登录</el-button>
      </el-form>
    </section>
  </main>
</template>
