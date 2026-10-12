import { apiClient, type ApiResponse } from './client'

export type CodexTaskType = 'IMPLEMENT' | 'FIX' | 'TESTS'
export type CodexStatus = 'PENDING_APPROVAL' | 'DISPATCHING' | 'DISPATCHED' | 'FAILED' | 'CANCELLED'
export interface CodexJob {
  id: string
  userId: number
  repository: string
  taskType: CodexTaskType
  prompt: string
  status: CodexStatus
  errorCode: string | null
  approvedBy: number | null
  approvedAt: string | null
  createdAt: string
  updatedAt: string
}
export interface CodexCapabilities {
  enabled: boolean
  repository: string
  workflow: string
  requiresApproval: boolean
  execution: string
  note: string
}
export interface CodexExecution {
  status: string
  conclusion: string
  url: string
  pullRequestUrl: string | null
}
export interface CodexDetail { job: CodexJob; execution: CodexExecution | null }

const base = '/ai/codex/requests'
export async function getCodexCapabilities(): Promise<CodexCapabilities> {
  return (await apiClient.get<ApiResponse<CodexCapabilities>>(`${base}/capabilities`)).data.data
}
export async function listCodexJobs(): Promise<CodexJob[]> {
  return (await apiClient.get<ApiResponse<CodexJob[]>>(base)).data.data
}
export async function getCodexJob(id: string): Promise<CodexDetail> {
  return (await apiClient.get<ApiResponse<CodexDetail>>(`${base}/${encodeURIComponent(id)}`)).data.data
}
export async function createCodexJob(taskType: CodexTaskType,prompt: string): Promise<CodexJob> {
  return (await apiClient.post<ApiResponse<CodexJob>>(base,{taskType,prompt})).data.data
}
export async function approveCodexJob(id: string): Promise<CodexJob> {
  return (await apiClient.post<ApiResponse<CodexJob>>(`${base}/${encodeURIComponent(id)}/approve`,
    {confirmation:'APPROVE_CODEX_JOB'})).data.data
}
export async function cancelCodexJob(id: string): Promise<CodexJob> {
  return (await apiClient.post<ApiResponse<CodexJob>>(`${base}/${encodeURIComponent(id)}/cancel`)).data.data
}
