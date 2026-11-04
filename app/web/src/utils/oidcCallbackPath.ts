/** Identify the *exact* PRP first-party OIDC redirect route.
 * A failed PRP session must never copy code/state from this callback into
 * the login redirect query, browser history, or another origin.
 */
export function isFirstPartyOidcCallbackPath(
  pathname: string, basePath: string,
): boolean {
  if (!basePath.startsWith('/') || !basePath.endsWith('/')) return false
  return pathname === `${basePath}me/mcp-link/callback`
}
