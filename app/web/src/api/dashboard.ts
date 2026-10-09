import { apiClient, type ApiResponse } from './client'

export interface DashboardModule {
  code: string
  name: string
  description: string
  enabled: boolean
}

export interface DashboardTask {
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

export interface DashboardRecord {
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

export interface DashboardSummary {
  date: string
  todayTaskCount: number
  overdueTaskCount: number
  unscheduledTaskCount: number
  recentRecordCount: number
  monthlyIncome: string
  monthlyExpense: string
  monthlyBalance: string
  todayTasks: DashboardTask[]
  overdueTasks: DashboardTask[]
  unscheduledTasks: DashboardTask[]
  highPriorityTasks: DashboardTask[]
  recentRecords: DashboardRecord[]
  modules: DashboardModule[]
}

export async function fetchDashboardSummary() {
  const response = await apiClient.get<ApiResponse<DashboardSummary>>('/dashboard/summary')
  return response.data.data
}
