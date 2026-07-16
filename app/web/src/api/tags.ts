import { apiClient, type ApiResponse } from './client'

export interface TagItem {
  id: number
  name: string
  color: string
  description: string
  createdAt: string
}

export interface CreateTagRequest {
  name: string
  color: string
  description: string
}

export type UpdateTagRequest = CreateTagRequest

export async function fetchTags() {
  const response = await apiClient.get<ApiResponse<TagItem[]>>('/tags')
  return response.data.data
}

export async function createTag(payload: CreateTagRequest) {
  const response = await apiClient.post<ApiResponse<TagItem>>('/tags', payload)
  return response.data.data
}

export async function updateTag(id: number, payload: UpdateTagRequest) {
  const response = await apiClient.put<ApiResponse<TagItem>>(`/tags/${id}`, payload)
  return response.data.data
}

export async function deleteTag(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/tags/${id}`)
}
