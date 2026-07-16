import { apiClient, type ApiResponse } from './client'

export interface ModuleItem {
  code: string
  name: string
  description: string
  type: 'feature' | 'domain'
  sortOrder: number
  enabled: boolean
}

export const fallbackDomainModules: ModuleItem[] = [
  { code: 'life', name: '生活', description: '日常、习惯、健康和家庭事务', type: 'domain', sortOrder: 110, enabled: true },
  { code: 'learning', name: '学习', description: '课程、考试、证书和成长记录', type: 'domain', sortOrder: 120, enabled: true },
  { code: 'work', name: '工作', description: '项目、会议、任务和职业成长', type: 'domain', sortOrder: 130, enabled: true },
  { code: 'interests', name: '兴趣', description: '阅读、旅行、音乐和长期爱好', type: 'domain', sortOrder: 140, enabled: true },
  { code: 'social', name: '社交', description: '联系人、互动和关系维护', type: 'domain', sortOrder: 150, enabled: true },
  { code: 'finance', name: '财务', description: '收入、支出、账单和财务复盘', type: 'domain', sortOrder: 160, enabled: true },
]

export async function fetchDomainModules() {
  const response = await apiClient.get<ApiResponse<ModuleItem[]>>('/modules/domains')
  return response.data.data
}
