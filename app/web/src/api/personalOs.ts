import { apiClient, type ApiResponse } from './client'

export type GoalStatus = 'PLANNED' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'CANCELLED'
export type MemorySensitivity = 'NORMAL' | 'SENSITIVE' | 'RESTRICTED'
export type MemoryPredicate = 'PREFERS' | 'DECLARES_SKILL' | 'HAS_BACKGROUND'

export interface PersonalGoal {
  id: number
  title: string
  description: string | null
  domain: string
  status: GoalStatus
  priority: 'low' | 'medium' | 'high'
  successCriteria: string | null
  targetDate: string | null
  createdAt: string
  updatedAt: string
}

export interface PersonalGoalCreate {
  title: string
  description: string | null
  domain: string
  priority: PersonalGoal['priority']
  successCriteria: string | null
  targetDate: string | null
  requestKey: string
}

export interface PersonalGoalLink {
  assertionId: number
  predicate: string
  subjectType: string
  subjectRef: string
  objectType: string
  objectRef: string | null
  objectValue: string | null
}

export interface PersonalMemory {
  id: number
  subjectType: string
  subjectRef: string
  predicate: string
  objectType: string
  objectRef: string | null
  objectValue: string | null
  sourceType: string
  sourceRef: string | null
  origin: string
  status: 'PENDING' | 'CONFIRMED' | 'SUPERSEDED' | 'INVALID'
  sensitivity: MemorySensitivity
  validFrom: string | null
  validTo: string | null
  supersedesId: number | null
  createdAt: string
}

export interface MemoryProposal {
  subjectType: 'PERSON'
  subjectRef: string
  predicate: MemoryPredicate
  objectType: 'LITERAL'
  objectRef: null
  objectValue: string
  sourceType: 'USER_INPUT'
  sourceRef: null
  validFrom: null
  validTo: null
  sensitivity: MemorySensitivity
  requestKey: string
}

export async function fetchPersonalGoals() {
  const { data } = await apiClient.get<ApiResponse<PersonalGoal[]>>('/goals')
  return data.data
}

export async function createPersonalGoal(input: PersonalGoalCreate) {
  const { data } = await apiClient.post<ApiResponse<PersonalGoal>>('/goals', input)
  return data.data
}

export async function changePersonalGoalStatus(id: number, status: GoalStatus) {
  const { data } = await apiClient.patch<ApiResponse<PersonalGoal>>(
    `/goals/${id}/status`, null, { params: { status } },
  )
  return data.data
}

export async function fetchPersonalGoalContext(id: number) {
  const { data } = await apiClient.get<ApiResponse<PersonalGoalLink[]>>(`/goals/${id}/context`)
  return data.data
}

export async function fetchConfirmedMemories() {
  const { data } = await apiClient.get<ApiResponse<PersonalMemory[]>>('/memory')
  return data.data
}

// Private confirmed facts are requested only by an explicit user action.
export async function fetchPrivateMemories() {
  const { data } = await apiClient.get<ApiResponse<PersonalMemory[]>>('/memory/private')
  return data.data
}

export async function fetchMemoryCandidates() {
  const { data } = await apiClient.get<ApiResponse<PersonalMemory[]>>('/memory/candidates')
  return data.data
}

export async function proposePersonalMemory(input: MemoryProposal) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>('/memory/candidates', input)
  return data.data
}

export async function replacePersonalMemory(id: number, input: MemoryProposal) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>(
    `/memory/${id}/replacement`, input,
  )
  return data.data
}

export async function confirmPersonalMemory(id: number) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>(`/memory/${id}/confirm`)
  return data.data
}

export async function invalidatePersonalMemory(id: number) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>(`/memory/${id}/invalidate`)
  return data.data
}

export async function erasePersonalMemory(id: number) {
  await apiClient.delete<ApiResponse<void>>(`/memory/${id}`)
}
