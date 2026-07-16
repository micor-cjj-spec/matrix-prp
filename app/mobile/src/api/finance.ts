import { request } from './client'

export interface FinanceMonthlySummary {
  income: string
  expense: string
  balance: string
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

export function fetchFinanceMonthlySummary(month?: string) {
  return request<FinanceMonthlySummary>({
    method: 'GET',
    url: `/finance/summary/monthly${month ? `?month=${encodeURIComponent(month)}` : ''}`,
  })
}

export function fetchFinanceAccountSummary(month?: string) {
  return request<FinanceAccountSummary[]>({
    method: 'GET',
    url: `/finance/summary/monthly/accounts${month ? `?month=${encodeURIComponent(month)}` : ''}`,
  })
}

export function fetchFinanceAccounts() {
  return request<FinanceAccountItem[]>({
    method: 'GET',
    url: '/finance/accounts',
  })
}

export function fetchFinanceCategories(type?: string) {
  return request<FinanceCategoryItem[]>({
    method: 'GET',
    url: `/finance/categories${type ? `?type=${encodeURIComponent(type)}` : ''}`,
  })
}

export function createFinanceTransaction(payload: {
  type: string
  amount: string
  category: string
  account: string
  merchant?: string
  note?: string
  transactionDate?: string
}) {
  return request<{ id: number; amount: string }>({
    method: 'POST',
    url: '/finance/transactions',
    data: payload,
  })
}
