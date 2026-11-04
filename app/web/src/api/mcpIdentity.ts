import { apiClient, type ApiResponse } from './client'

export interface McpIdentityLink {
  issuer: string
  subject: string
  newlyLinked: boolean
}
export interface McpLinkTicket {
  code: string
  clientId: string
  expiresAt: string
}

export async function listMcpIdentityLinks(): Promise<McpIdentityLink[]> {
  const response = await apiClient.get<ApiResponse<McpIdentityLink[]>>('/mcp/identity')
  return response.data.data
}

export async function createMcpIdentityTicket(clientId: string, password: string): Promise<McpLinkTicket> {
  const response = await apiClient.post<ApiResponse<McpLinkTicket>>(
    '/mcp/identity/tickets', { clientId, password })
  return response.data.data
}

export async function unlinkMcpIdentity(password: string): Promise<void> {
  await apiClient.post('/mcp/identity/unlink', { password })
}
