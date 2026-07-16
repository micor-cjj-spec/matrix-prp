import { apiClient, type ApiResponse } from './client'

export interface RuntimeHealth {
  status: string
  persistence: string
  database: string
  knowledgeRoot: string
  knowledgeAvailable: boolean
  activeProfiles: string[]
}

export async function fetchRuntimeHealth() {
  const response = await apiClient.get<ApiResponse<RuntimeHealth>>('/health/runtime')
  return response.data.data
}
