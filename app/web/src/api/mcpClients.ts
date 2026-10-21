import { apiClient, type ApiResponse } from './client'

export const mcpScopes = [
  { value: 'prp.tasks.read', label: '读取任务' },
  { value: 'prp.finance.read', label: '读取财务' },
  { value: 'prp.wellness.read', label: '读取健康记录' },
  { value: 'prp.write.create', label: '生成待确认草稿' },
  { value: 'prp.write.status', label: '查看草稿状态' },
  { value: 'prp.write.confirm', label: '提交已在 PRP 审批的草稿' },
] as const

export interface McpClientGrant {
  clientId: string
  scopes: string[]
  status: 'ACTIVE' | 'REVOKED'
}

export async function listMcpClients(): Promise<McpClientGrant[]> {
  const response = await apiClient.get<ApiResponse<McpClientGrant[]>>('/mcp/clients')
  return response.data.data
}

export async function authorizeMcpClient(clientId: string, scopes: string[], password: string): Promise<McpClientGrant> {
  const response = await apiClient.post<ApiResponse<McpClientGrant>>('/mcp/clients', { clientId, scopes, password })
  return response.data.data
}

export async function revokeMcpClient(clientId: string): Promise<void> {
  await apiClient.post('/mcp/clients/revoke', { clientId })
}
