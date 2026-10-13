/** Frontend navigation guard only. Backend still checks every administrator API. */
export interface AdminSession {
  readonly isAuthenticated: boolean
  readonly user: { administrator: boolean } | null
  loadCurrentUser(): Promise<void>
}

export type AdminDecision = 'allowed' | 'unauthenticated' | 'forbidden' | 'unavailable'

export async function ensureAdminAccess(session: AdminSession): Promise<AdminDecision> {
  if (!session.isAuthenticated) return 'unauthenticated'
  if (!session.user) {
    try {
      await session.loadCurrentUser()
    } catch {
      return session.isAuthenticated ? 'unavailable' : 'unauthenticated'
    }
  }
  if (!session.isAuthenticated) return 'unauthenticated'
  return session.user?.administrator ? 'allowed' : 'forbidden'
}
