export interface LoginResponse {
  token: string
  user: {
    id: number
    username: string
    displayName: string
  }
}

export interface UserProfile {
  id: number
  username: string
  displayName: string
}

export interface HealthStatus {
  status: string
  service: string
  version: string
  apiContract: string
  time: string
}

export interface RuntimeHealth {
  status: string
  persistence: string
  database: string
  knowledgeRoot: string
  knowledgeAvailable: boolean
  activeProfiles: string[]
}

export interface DashboardSummary {
  date: string
  todayTaskCount: number
  overdueTaskCount: number
  recentRecordCount: number
  monthlyIncome: string
  monthlyExpense: string
  monthlyBalance: string
  todayTasks: TaskItem[]
  highPriorityTasks: TaskItem[]
  recentRecords: RecordItem[]
}

export interface RecordItem {
  id: number
  moduleCode: string
  title: string
  content: string
  recordDate: string
  tags: Array<{
    id: number
    name: string
    color: string
  }>
}

export interface TaskItem {
  id: number
  moduleCode: string
  title: string
  description: string
  priority: string
  status: string
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

export interface FinanceTransactionItem {
  id: number
  type: string
  amount: string
  category: string
  account: string
  transactionDate: string
  note: string
}

export interface FinanceMonthlySummary {
  income: string
  expense: string
  balance: string
}

export interface FinanceCategorySummary {
  category: string
  amount: string
  ratio: string
}

export interface FinanceAccountSummary {
  account: string
  income: string
  expense: string
  balance: string
}

export interface FinanceAccountItem {
  id: number
  name: string
  type: string
  currency: string
  openingBalance: string
  note: string
  createdAt: string
}

export interface FinanceCategoryItem {
  id: number
  name: string
  type: string
  color: string
  note: string
  createdAt: string
}

export interface ReviewItem {
  id: number
  reviewType: string
  moduleCode: string
  title: string
  summary: string
  periodStart: string
  periodEnd: string
}

export interface ModuleItem {
  code: string
  name: string
  description: string
  type: string
  sortOrder: number
  enabled: boolean
}

export interface TagItem {
  id: number
  name: string
  color: string
  description: string
  createdAt: string
}

export interface KnowledgeSearchResult {
  path: string
  name: string
  snippet: string
  score: number
}

export interface KnowledgeFile {
  path: string
  name: string
  content: string
}

export interface KnowledgeNode {
  name: string
  path: string
  type: 'directory' | 'file'
  children: KnowledgeNode[]
}

export interface KnowledgeStats {
  fileCount: number
  directoryCount: number
  totalBytes: number
}
