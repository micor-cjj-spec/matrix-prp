import { apiClient, type ApiResponse } from './client'

export type AgentTaskType = 'PLAN' | 'SUMMARIZE' | 'ANALYZE'
export type AgentTaskStatus = 'PENDING_APPROVAL' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
export interface AgentTask {
  id: string
  userId: number
  taskType: AgentTaskType
  prompt: string
  status: AgentTaskStatus
  result: string | null
  errorCode: string | null
  createdAt: string
  updatedAt: string
  approvedBy: number | null
  approvedAt: string | null
  sessionRef: string
}
export interface AgentCapabilities {
  openclawEnabled: boolean
  codexEnabled: boolean
  requiresApproval: boolean
  mode: string
  message: string
}
export async function getAgentCapabilities() {
  return (await apiClient.get<ApiResponse<AgentCapabilities>>('/ai/agent/capabilities')).data.data
}
export async function listAgentTasks() {
  return (await apiClient.get<ApiResponse<AgentTask[]>>('/ai/agent/tasks')).data.data
}
export async function createAgentTask(taskType: AgentTaskType, prompt: string) {
  return (await apiClient.post<ApiResponse<AgentTask>>('/ai/agent/tasks', { taskType, prompt })).data.data
}
export async function approveAgentTask(id: string) {
  return (await apiClient.post<ApiResponse<AgentTask>>(
    `/ai/agent/tasks/${encodeURIComponent(id)}/approve`,
    { confirmation: 'APPROVE_AGENT_TASK' })).data.data
}
export async function cancelAgentTask(id: string) {
  return (await apiClient.post<ApiResponse<AgentTask>>(
    `/ai/agent/tasks/${encodeURIComponent(id)}/cancel`)).data.data
}
