import { apiClient, type ApiResponse } from './client'

export interface FinanceImportRow {
  id: number
  sourceLine: number
  transactionAt: string
  transactionType: string
  counterparty: string
  description: string
  direction: string
  amount: number
  paymentMethod: string
  originalStatus: string
  sourceTransactionId: string
  rowStatus: 'READY' | 'REVIEW' | 'DUPLICATE' | 'POSTED'
}

export interface FinanceImportBatch {
  id: number
  platform: string
  sourceAccountKey: string
  filename: string
  status: string
  ready: number
  review: number
  duplicate: number
  posted: number
  rows: FinanceImportRow[]
}

export interface FinanceImportHistory {
  id: number
  platform: string
  sourceAccountKey: string
  filename: string
  status: string
  createdAt: string
}

export async function previewWeChatBill(file: File, sourceAccountKey: string): Promise<FinanceImportBatch> {
  const form = new FormData()
  form.append('file', file)
  if (sourceAccountKey.trim()) form.append('sourceAccountKey', sourceAccountKey.trim())
  const response = await apiClient.post<ApiResponse<FinanceImportBatch>>('/finance/imports/wechat/preview', form)
  return response.data.data
}

export async function getFinanceImport(id: number): Promise<FinanceImportBatch> {
  const response = await apiClient.get<ApiResponse<FinanceImportBatch>>(`/finance/imports/${id}`)
  return response.data.data
}

export async function listFinanceImports(): Promise<FinanceImportHistory[]> {
  const response = await apiClient.get<ApiResponse<FinanceImportHistory[]>>('/finance/imports')
  return response.data.data
}

export async function commitFinanceImport(id: number, paymentAccounts: Record<string, number>): Promise<FinanceImportBatch> {
  const response = await apiClient.post<ApiResponse<FinanceImportBatch>>(
    `/finance/imports/${id}/commit`, { paymentAccounts },
  )
  return response.data.data
}
