/** Only a rejected /users/me token proves that the persisted session expired.
 * Timeouts, offline errors, and 5xx outages must leave the token untouched. */
export function isUserSessionExpired(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const response = (error as { response?: { status?: unknown } }).response
  return response?.status === 401
}
