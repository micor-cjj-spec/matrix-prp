import { apiClient, type ApiResponse } from './client'

export { mcpScopes } from './mcpScopes'

export interface McpClientGrant {
  clientId: string
  scopes: string[]
  status: 'ACTIVE' | 'REVOKED' | 'EXPIRED'
}

export async function listMcpClients(): Promise<McpClientGrant[]> {
  const response = await apiClient.get<ApiResponse<McpClientGrant[]>>('/mcp/clients')
  return response.data.data
}

export async function authorizeMcpClient(clientId: string, scopes: string[], password: string): Promise<McpClientGrant> {
  const response = await apiClient.post<ApiResponse<McpClientGrant>>('/mcp/clients', { clientId, scopes, password })
  return response.data.data
}

/** Owner password required; only a ten-minute, task-read pairing grant. */
export async function authorizeTemporaryMcpPairing(clientId: string, password: string): Promise<McpClientGrant> {
  const response = await apiClient.post<ApiResponse<McpClientGrant>>('/mcp/clients/pairing', { clientId, password })
  return response.data.data
}

export async function revokeMcpClient(clientId: string): Promise<void> {
  await apiClient.post('/mcp/clients/revoke', { clientId })
}
