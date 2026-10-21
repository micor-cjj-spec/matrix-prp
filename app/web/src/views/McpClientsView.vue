<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/layouts/AppLayout.vue'
import {
  authorizeMcpClient, listMcpClients, mcpScopes, revokeMcpClient,
  type McpClientGrant,
} from '@/api/mcpClients'

const clients = ref<McpClientGrant[]>([])
const clientId = ref('')
const scopes = ref<string[]>(['prp.tasks.read'])
const password = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try { clients.value = await listMcpClients() }
  catch { error.value = '连接管理未启用或暂时不可用。请检查 PRP MCP OAuth 配置。' }
  finally { loading.value = false }
}

async function approve() {
  if (!clientId.value.trim() || !password.value || scopes.value.length === 0) return
  busy.value = true
  try {
    await authorizeMcpClient(clientId.value.trim(), scopes.value, password.value)
    password.value = ''
    ElMessage.success('已授权客户端指定权限')
    await refresh()
  } catch {
    password.value = ''
    ElMessage.error('授权失败，请核对账号密码、客户端 ID 和权限配置')
  } finally { busy.value = false }
}

async function revoke(client: McpClientGrant) {
  try { await ElMessageBox.confirm(
    '撤销后，此客户端新发起的 MCP 请求将被拒绝。确定撤销吗？',
    '撤销 MCP 客户端授权', { type: 'warning' },
  ) } catch { return }
  busy.value = true
  try { await revokeMcpClient(client.clientId); ElMessage.success('已撤销授权'); await refresh() }
  catch { ElMessage.error('撤销失败，请重试') }
  finally { busy.value = false }
}
onMounted(refresh)
</script>

<template>
  <AppLayout>
    <div class="mcp-clients">
      <RouterLink to="/me" class="back">‹ 返回我的</RouterLink>
      <header class="prp-section-header">
        <div><p class="eyebrow">MATRIX PRP / MCP</p><h1>MCP 客户端授权</h1>
          <p>控制外部 AI 客户端可使用的个人数据权限，授权可随时撤销。</p></div>
      </header>
      <el-alert type="warning" :closable="false" show-icon
        title="仅向已核实身份的 OAuth 客户端授权。此页面不会颁发 OAuth 令牌，也不能替代第三方账号关联。" />
      <el-card shadow="never" class="section">
        <template #header>新增或修改客户端授权</template>
        <el-form label-position="top" @submit.prevent="approve">
          <el-form-item label="OAuth 客户端 ID（从可信授权服务器获得）">
            <el-input v-model="clientId" maxlength="128" placeholder="OAuth client_id" autocomplete="off"/>
          </el-form-item>
          <el-form-item label="允许的权限">
            <el-checkbox-group v-model="scopes">
              <div v-for="scope in mcpScopes" :key="scope.value" class="scope-option">
                <el-checkbox :value="scope.value" :label="scope.label" />
              </div>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="再次输入 PRP 账号密码确认授权">
            <el-input v-model="password" type="password" show-password autocomplete="current-password"
              maxlength="256" placeholder="密码只发送给 PRP，不提供给 AI 客户端" />
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="busy"
            :disabled="!clientId.trim() || !password || scopes.length === 0 || busy">批准此客户端</el-button>
        </el-form>
      </el-card>
      <el-card shadow="never" class="section">
        <template #header>已登记的客户端</template>
        <el-skeleton v-if="loading" :rows="3" animated />
        <el-alert v-else-if="error" type="info" :closable="false" :title="error" />
        <el-empty v-else-if="!clients.length" description="尚无已授权客户端" />
        <div v-for="client in clients" v-else :key="client.clientId" class="client-row">
          <div class="client-info">
            <strong>{{ client.clientId }}</strong>
            <p>{{ client.scopes.map(scope => mcpScopes.find(s => s.value === scope)?.label ?? scope).join('、') }}</p>
            <el-tag size="small" :type="client.status === 'ACTIVE' ? 'success' : 'info'">
              {{ client.status === 'ACTIVE' ? '已授权' : '已撤销' }}
            </el-tag>
          </div>
          <el-button v-if="client.status === 'ACTIVE'" type="danger" plain :loading="busy"
            @click="revoke(client)">撤销授权</el-button>
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>

<style scoped>
.mcp-clients{max-width:860px;margin:0 auto;padding-bottom:32px}
.back{display:inline-block;margin-bottom:16px;text-decoration:none;color:var(--el-color-primary)}
.section{margin-top:20px}.scope-option{margin-bottom:6px}
.client-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 0;border-bottom:1px solid var(--el-border-color-lighter)}
.client-row:last-child{border-bottom:none}.client-info{min-width:0}
.client-info strong,.client-info p{overflow-wrap:anywhere}.client-info p{color:var(--el-text-color-secondary);font-size:13px}
</style>
