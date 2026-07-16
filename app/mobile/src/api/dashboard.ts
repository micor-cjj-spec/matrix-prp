import { request } from './client'
import type { RecordItem } from './records'
import type { TaskItem } from './tasks'

export interface DashboardSummary {
  date: string
  todayTaskCount: number
  overdueTaskCount: number
  recentRecordCount: number
  monthlyIncome: string | number
  monthlyExpense: string | number
  monthlyBalance: string | number
  todayTasks: TaskItem[]
  highPriorityTasks: TaskItem[]
  recentRecords: RecordItem[]
}

export function fetchDashboardSummary() {
  return request<DashboardSummary>({
    method: 'GET',
    url: '/dashboard/summary',
  })
}
