import { apiClient, type ApiResponse } from './client'

export interface RecordItem {
  id: number
  moduleCode: string
  title: string
  content: string
  recordDate: string
  createdAt: string
  tags: Array<{
    id: number
    name: string
    color: string
  }>
}

export interface CreateRecordRequest {
  moduleCode: string
  title: string
  content: string
  recordDate?: string
  tagIds?: number[]
}

export interface RecordFilterParams {
  moduleCode?: string
  tagId?: number
  recordDate?: string
  keyword?: string
}

export async function fetchRecords(params: RecordFilterParams = {}) {
  const response = await apiClient.get<ApiResponse<RecordItem[]>>('/records', { params })
  return response.data.data
}

export async function createRecord(payload: CreateRecordRequest) {
  const response = await apiClient.post<ApiResponse<RecordItem>>('/records', payload)
  return response.data.data
}

export async function updateRecord(id: number, payload: CreateRecordRequest) {
  const response = await apiClient.put<ApiResponse<RecordItem>>(`/records/${id}`, payload)
  return response.data.data
}

export async function deleteRecord(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/records/${id}`)
}
