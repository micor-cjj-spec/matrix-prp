import { apiClient, type ApiResponse } from './client'

export interface FinanceTransactionItem {
  id: number
  type: string
  amount: string
  category: string
  account: string
  merchant: string
  note: string
  transactionDate: string
  createdAt: string
}

export interface CreateFinanceTransactionRequest {
  type: string
  amount: number
  category: string
  account: string
  merchant: string
  note: string
  transactionDate?: string
}

export interface FinanceTransactionFilterParams {
  month?: string
  type?: string
  category?: string
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

export interface CreateFinanceAccountRequest {
  name: string
  type: string
  currency: string
  openingBalance: number
  note: string
}

export interface FinanceCategoryItem {
  id: number
  name: string
  type: string
  color: string
  note: string
  createdAt: string
}

export interface CreateFinanceCategoryRequest {
  name: string
  type: string
  color: string
  note: string
}

export async function fetchFinanceTransactions(params: FinanceTransactionFilterParams = {}) {
  const response = await apiClient.get<ApiResponse<FinanceTransactionItem[]>>('/finance/transactions', { params })
  return response.data.data
}

export async function createFinanceTransaction(payload: CreateFinanceTransactionRequest) {
  const response = await apiClient.post<ApiResponse<FinanceTransactionItem>>('/finance/transactions', payload)
  return response.data.data
}

export async function updateFinanceTransaction(id: number, payload: CreateFinanceTransactionRequest) {
  const response = await apiClient.put<ApiResponse<FinanceTransactionItem>>(`/finance/transactions/${id}`, payload)
  return response.data.data
}

export async function deleteFinanceTransaction(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/finance/transactions/${id}`)
}

export async function fetchFinanceMonthlySummary(month?: string) {
  const response = await apiClient.get<ApiResponse<FinanceMonthlySummary>>('/finance/summary/monthly', {
    params: { month },
  })
  return response.data.data
}

export async function fetchFinanceCategorySummary(month?: string) {
  const response = await apiClient.get<ApiResponse<FinanceCategorySummary[]>>('/finance/summary/monthly/categories', {
    params: { month },
  })
  return response.data.data
}

export async function fetchFinanceAccountSummary(month?: string) {
  const response = await apiClient.get<ApiResponse<FinanceAccountSummary[]>>('/finance/summary/monthly/accounts', {
    params: { month },
  })
  return response.data.data
}

export async function fetchFinanceAccounts() {
  const response = await apiClient.get<ApiResponse<FinanceAccountItem[]>>('/finance/accounts')
  return response.data.data
}

export async function createFinanceAccount(payload: CreateFinanceAccountRequest) {
  const response = await apiClient.post<ApiResponse<FinanceAccountItem>>('/finance/accounts', payload)
  return response.data.data
}

export async function updateFinanceAccount(id: number, payload: CreateFinanceAccountRequest) {
  const response = await apiClient.put<ApiResponse<FinanceAccountItem>>(`/finance/accounts/${id}`, payload)
  return response.data.data
}

export async function deleteFinanceAccount(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/finance/accounts/${id}`)
}

export async function fetchFinanceCategories(type?: string) {
  const response = await apiClient.get<ApiResponse<FinanceCategoryItem[]>>('/finance/categories', {
    params: { type },
  })
  return response.data.data
}

export async function createFinanceCategory(payload: CreateFinanceCategoryRequest) {
  const response = await apiClient.post<ApiResponse<FinanceCategoryItem>>('/finance/categories', payload)
  return response.data.data
}

export async function updateFinanceCategory(id: number, payload: CreateFinanceCategoryRequest) {
  const response = await apiClient.put<ApiResponse<FinanceCategoryItem>>(`/finance/categories/${id}`, payload)
  return response.data.data
}

export async function deleteFinanceCategory(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/finance/categories/${id}`)
}

export interface FinanceAccountBalance {
  accountId: number
  account: string
  currency: string
  openingBalance: string
  income: string
  expense: string
  transferIn: string
  transferOut: string
  currentBalance: string
}
export interface FinanceTransferItem {
  id: number
  fromAccountId: number
  fromAccount: string
  toAccountId: number
  toAccount: string
  amount: string
  currency: string
  transferDate: string
  note: string
}
export interface CreateFinanceTransferRequest {
  fromAccountId: number
  toAccountId: number
  amount: number
  transferDate: string
  note: string
  clientRequestId: string
}
export async function fetchFinanceAccountBalances() {
  const response = await apiClient.get<ApiResponse<FinanceAccountBalance[]>>('/finance/accounts/balances')
  return response.data.data
}
export async function fetchFinanceTransfers() {
  const response = await apiClient.get<ApiResponse<FinanceTransferItem[]>>('/finance/transfers')
  return response.data.data
}
export async function createFinanceTransfer(payload: CreateFinanceTransferRequest) {
  const response = await apiClient.post<ApiResponse<FinanceTransferItem>>('/finance/transfers', payload)
  return response.data.data
}
export async function deleteFinanceTransfer(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/finance/transfers/${id}`)
}
