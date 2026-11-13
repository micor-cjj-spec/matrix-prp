<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { finishFirstPartyOidcLink } from '@/api/mcpFirstPartyOidc'
import { getStoredToken } from '@/utils/token'

const loading = ref(true)
const success = ref(false)
const error = ref('')

onMounted(async () => {
  // Read callback parameters in-memory, then scrub the address bar BEFORE
  // any asynchronous work. Never log the authorization code or state.
  const params = new URLSearchParams(window.location.search)
  const code = params.getAll('code')
  const state = params.getAll('state')
  const issuers = params.getAll('iss')
  const oauthError = params.getAll('error')
  window.history.replaceState(window.history.state, '', window.location.pathname)
  if (oauthError.length || code.length !== 1 || state.length !== 1 || issuers.length !== 1
    || !code[0] || !state[0] || !issuers[0]) {
    error.value = 'Keycloak 未返回完整、唯一的授权结果。请重新从 PRP 发起绑定。'
    loading.value = false
    return
  }
  // Do NOT redirect to login with code/state in the URL; a pending attempt
  // should expire if the original PRP session is no longer available.
  if (!getStoredToken()) {
    error.value = '原 PRP 登录会话已结束。为了安全，请重新登录 PRP 后发起新的绑定。'
    loading.value = false
    return
  }
  try {
    await finishFirstPartyOidcLink(state[0], code[0], issuers[0])
    success.value = true
  } catch {
    error.value = 'Keycloak 身份校验或 PRP 账号绑定失败。请检查授权是否已撤销、绑定是否冲突，重新发起新的绑定。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="oidc-link-result">
    <section class="oidc-link-panel">
      <h1>PRP · Keycloak 身份绑定</h1>
      <p v-if="loading">正在验证 Keycloak 签名和一次性授权状态…</p>
      <el-alert v-else-if="success" title="身份验证和绑定成功" type="success"
        description="现在可以在完成正式 ChatGPT OAuth 授权后，尝试读取自己的 PRP 任务。" :closable="false" />
      <el-alert v-else :title="error" type="error" :closable="false" />
      <RouterLink to="/me/mcp-clients">返回 MCP 客户端授权</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.oidc-link-result{min-height:60vh;display:grid;place-items:center;padding:24px}
.oidc-link-panel{max-width:550px;width:100%;display:grid;gap:18px}
.oidc-link-panel h1{margin:0;font-size:22px}
</style>
