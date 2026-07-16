import { request } from './client'

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

export function fetchRecords() {
  return request<RecordItem[]>({
    method: 'GET',
    url: '/records',
  })
}

export function createRecord(payload: {
  moduleCode: string
  title: string
  content: string
  recordDate?: string
}) {
  return request<{ id: number; title: string }>({
    method: 'POST',
    url: '/records',
    data: payload,
  })
}
