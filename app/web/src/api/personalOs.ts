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

/** Explicit first-party owner association. Does not create or change a task. */
export async function proposeGoalTaskLink(goalId: number, taskId: number, key: string) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>(
    '/memory/candidates', {
      subjectType: 'TASK',
      subjectRef: String(taskId),
      predicate: 'ADVANCES',
      objectType: 'GOAL',
      objectRef: String(goalId),
      objectValue: null,
      sourceType: 'TASK',
      sourceRef: String(taskId),
      validFrom: null,
      validTo: null,
      sensitivity: 'NORMAL',
      requestKey: key,
    },
  )
  // Remains PENDING until a separate, explicit first-party confirmation.
  return data.data
}

/** Separate owner-reviewed link of an existing review to one personal goal. */
export async function proposeGoalReviewLink(goalId: number, reviewId: number, key: string) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory>>(
    '/memory/candidates', {
      subjectType: 'REVIEW',
      subjectRef: String(reviewId),
      predicate: 'EVALUATES',
      objectType: 'GOAL',
      objectRef: String(goalId),
      objectValue: null,
      sourceType: 'REVIEW',
      sourceRef: String(reviewId),
      validFrom: null,
      validTo: null,
      sensitivity: 'NORMAL',
      requestKey: key,
    },
  )
  // Unlike a data-entry form this creates only an unconfirmed association.
  return data.data
}

/** T-005: personal-goal model sharing is separate from normal chat/MCP scopes. */
export interface PlanningEvidence {
  reference: string
  relation: string
  statement: string
  evidenceClass: string
}
export interface PlanningGap {
  code: string
  explanation: string
}
export interface PlanningTaskDraft {
  title: string
  rationale: string
  evidenceRefs: string[]
}
export interface PlanningSnapshot {
  goalId: number
  title: string
  status: string
  successCriteria: string | null
  evidence: PlanningEvidence[]
  gaps: PlanningGap[]
  taskDrafts: PlanningTaskDraft[]
  modelInvoked: boolean
  dataWritten: boolean
  limitation: string
}
export interface PlanningModelReview {
  previewId: string
  goalId: number
  provider: string
  model: string
  snapshot: PlanningSnapshot
  expiresAtMillis: number
}
export interface PlanningModelProposal {
  title: string
  rationale: string
  evidenceRefs: string[]
  assumptions: string[]
}
export interface PlanningModelAdvice {
  goalId: number
  provider: string
  model: string
  proposals: PlanningModelProposal[]
  evidence: PlanningEvidence[]
  gaps: PlanningGap[]
  dataWritten: boolean
  limitation: string
}

export async function previewGoalModelSharing(id: number, includePersonalFacts: boolean) {
  const { data } = await apiClient.post<ApiResponse<PlanningModelReview>>(
    `/ai/personal-os/goals/${id}/model/preview`, { includePersonalFacts },
  )
  return data.data
}

export async function confirmGoalModelSharing(id: number, previewId: string) {
  const { data } = await apiClient.post<ApiResponse<{ modelToken: string }>>(
    `/ai/personal-os/goals/${id}/model/confirm`, { previewId },
  )
  return data.data.modelToken
}

export async function suggestGoalModelAdvice(id: number, modelToken: string) {
  const { data } = await apiClient.post<ApiResponse<PlanningModelAdvice>>(
    `/ai/personal-os/goals/${id}/model/suggest`, { modelToken },
    { timeout: 155000 }, // Model streaming is server-side; keep the rest of the API at 8s.
  )
  return data.data
}

/** Submits unverified AI proposals only to owner-review PENDING, not confirmed memory. */
export interface PersonalAiKnowledgeCandidate {
  predicate: MemoryPredicate
  value: string
  validFrom: null
  validTo: null
  sensitivity: 'RESTRICTED'
  requestKey: string
  sourceMessageId?: number
  evidenceQuote?: string
}
export async function submitPersonalAiKnowledgeCandidates(items: PersonalAiKnowledgeCandidate[]) {
  const { data } = await apiClient.post<ApiResponse<PersonalMemory[]>>(
    '/memory/ai-candidates', items,
  )
  return data.data
}

/** Explicit authenticated user-click read; never fetched for default model context. */
export interface ChatEvidenceSource {
  messageId: number
  messageText: string
  sentAt: string
}
export async function fetchMemoryChatSource(assertionId: number) {
  return (await apiClient.get<ApiResponse<ChatEvidenceSource>>(
    `/memory/${assertionId}/source-preview`,
  )).data.data
}

/** Private, owner-scoped, read-only preflight; no raw existing fact values are returned. */
export type AiKnowledgeDisposition = 'NEW' | 'DUPLICATE' | 'POSSIBLY_RELATED' | 'REVIEW_REQUIRED'
export interface AiKnowledgeInspection {
  requestKey: string
  disposition: AiKnowledgeDisposition
}
export async function inspectPersonalAiKnowledgeCandidates(items: PersonalAiKnowledgeCandidate[]) {
  const { data } = await apiClient.post<ApiResponse<AiKnowledgeInspection[]>>(
    '/memory/ai-candidates/inspect', items,
  )
  return data.data
}

/** Requested only by a deliberate owner action, never as normal AI context. */
export async function fetchNormalMemoryHistory() {
  return (await apiClient.get<ApiResponse<PersonalMemory[]>>(
    '/memory/history/normal',
  )).data.data
}
