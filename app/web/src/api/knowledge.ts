import { apiClient, type ApiResponse } from './client'

export interface KnowledgeNode {
  name: string
  path: string
  type: 'directory' | 'file'
  children: KnowledgeNode[]
}

export interface KnowledgeFile {
  path: string
  name: string
  content: string
}

export interface KnowledgeSearchResult {
  path: string
  name: string
  snippet: string
  score: number
}

export interface KnowledgeStats {
  fileCount: number
  directoryCount: number
  totalBytes: number
}

export async function fetchKnowledgeTree() {
  const response = await apiClient.get<ApiResponse<KnowledgeNode[]>>('/knowledge/tree')
  return response.data.data
}

export async function fetchKnowledgeStats() {
  const response = await apiClient.get<ApiResponse<KnowledgeStats>>('/knowledge/stats')
  return response.data.data
}

export async function fetchKnowledgeFile(path: string) {
  const response = await apiClient.get<ApiResponse<KnowledgeFile>>('/knowledge/files', {
    params: { path },
  })
  return response.data.data
}

export async function searchKnowledge(q: string) {
  const response = await apiClient.get<ApiResponse<KnowledgeSearchResult[]>>('/knowledge/search', {
    params: { q },
  })
  return response.data.data
}
