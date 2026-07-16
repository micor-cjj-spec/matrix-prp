import { request } from './client'

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

export interface TaskFilterParams {
  status?: string
  moduleCode?: string
  dueDate?: string
  priority?: string
}

export interface CreateTaskRequest {
  moduleCode: string
  title: string
  description: string
  priority: string
  dueDate?: string
}

export interface TaskSummary {
  openCount: number
  todayCount: number
  overdueCount: number
  upcomingSevenDaysCount: number
  highPriorityOpenCount: number
  statusCounts: Record<string, number>
}

export function fetchTasks(params: TaskFilterParams = {}) {
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&')
  return request<TaskItem[]>({
    method: 'GET',
    url: query ? `/tasks?${query}` : '/tasks',
  })
}

export function fetchTaskSummary() {
  return request<TaskSummary>({
    method: 'GET',
    url: '/tasks/summary',
  })
}

export function createTask(payload: CreateTaskRequest) {
  return request<TaskItem>({
    method: 'POST',
    url: '/tasks',
    data: payload,
  })
}

export function updateTaskStatus(id: number, status: string) {
  return request<TaskItem>({
    method: 'PATCH' as UniApp.RequestOptions['method'],
    url: `/tasks/${id}/status?status=${encodeURIComponent(status)}`,
  })
}
