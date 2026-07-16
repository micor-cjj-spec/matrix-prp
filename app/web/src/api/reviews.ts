import { apiClient, type ApiResponse } from './client'

export interface ReviewItem {
  id: number
  reviewType: string
  moduleCode: string
  title: string
  summary: string
  highlights: string
  problems: string
  nextActions: string
  periodStart: string
  periodEnd: string
  createdAt: string
}

export interface CreateReviewRequest {
  reviewType: string
  moduleCode: string
  title: string
  summary: string
  highlights: string
  problems: string
  nextActions: string
  periodStart?: string
  periodEnd?: string
}

export interface ReviewFilter {
  reviewType?: string
  moduleCode?: string
  periodStart?: string
  periodEnd?: string
}

export async function fetchReviews(params?: ReviewFilter) {
  const response = await apiClient.get<ApiResponse<ReviewItem[]>>('/reviews', { params })
  return response.data.data
}

export async function createReview(payload: CreateReviewRequest) {
  const response = await apiClient.post<ApiResponse<ReviewItem>>('/reviews', payload)
  return response.data.data
}

export async function updateReview(id: number, payload: CreateReviewRequest) {
  const response = await apiClient.put<ApiResponse<ReviewItem>>(`/reviews/${id}`, payload)
  return response.data.data
}

export async function deleteReview(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/reviews/${id}`)
}
