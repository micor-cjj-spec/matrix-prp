import { apiClient, type ApiResponse } from './client'

export type McpDraftStatus = 'PENDING' | 'APPROVED' | 'CONSUMED' | 'REJECTED'
export interface McpDraftReview {
  draftId: string
  kind: 'TASK' | 'FINANCE' | 'RECORD'
  values: Record<string, unknown>
  status: McpDraftStatus
  expiresAt: string
}
export interface McpApprovalResult {
  status: 'APPROVED' | 'INVALID_PASSWORD' | 'LOCKED'
  remainingAttempts: number
}

export async function readMcpDraft(id: string): Promise<McpDraftReview> {
  const response = await apiClient.get<ApiResponse<McpDraftReview>>(`/mcp/approval/drafts/${encodeURIComponent(id)}`)
  return response.data.data
}

export async function approveMcpDraft(id: string, password: string): Promise<McpApprovalResult> {
  const response = await apiClient.post<ApiResponse<McpApprovalResult>>(
    `/mcp/approval/drafts/${encodeURIComponent(id)}/approve`, { password })
  return response.data.data
}

export async function rejectMcpDraft(id: string): Promise<void> {
  await apiClient.post(`/mcp/approval/drafts/${encodeURIComponent(id)}/reject`, {})
}
