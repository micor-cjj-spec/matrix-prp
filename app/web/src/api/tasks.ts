import { apiClient, type ApiResponse } from './client'

export interface TaskItem {
  id: number
  moduleCode: string
  title: string
  description: string
  priority: string
  status: string
  dueDate?: string
  createdAt: string
  completedAt?: string
}

export interface CreateTaskRequest {
  moduleCode: string
  title: string
  description: string
  priority: string
  dueDate?: string | null
}

export interface TaskFilterParams {
  status?: string
  moduleCode?: string
  dueDate?: string
  priority?: string
}

export interface TaskSummary {
  openCount: number
  todayCount: number
  unscheduledCount: number
  overdueCount: number
  upcomingSevenDaysCount: number
  highPriorityOpenCount: number
  statusCounts: Record<string, number>
}

export async function fetchTasks(params: TaskFilterParams = {}) {
  const response = await apiClient.get<ApiResponse<TaskItem[]>>('/tasks', { params })
  return response.data.data
}

export async function fetchTaskSummary() {
  const response = await apiClient.get<ApiResponse<TaskSummary>>('/tasks/summary')
  return response.data.data
}

export async function createTask(payload: CreateTaskRequest) {
  const response = await apiClient.post<ApiResponse<TaskItem>>('/tasks', payload)
  return response.data.data
}

export async function updateTask(id: number, payload: CreateTaskRequest) {
  const response = await apiClient.put<ApiResponse<TaskItem>>(`/tasks/${id}`, payload)
  return response.data.data
}

export async function updateTaskStatus(id: number, status: string) {
  const response = await apiClient.patch<ApiResponse<TaskItem>>(`/tasks/${id}/status`, null, {
    params: { status },
  })
  return response.data.data
}

export async function deleteTask(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/tasks/${id}`)
}
