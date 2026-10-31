/**
 * Never copy OAuth authorization codes/states/issuers into the unauthenticated
 * login route's `redirect` query. After login the owner must start a fresh
 * pairing request; old codes and tickets remain single-use and unconsumed.
 */
export function safeUnauthenticatedRedirect(route: {
  name?: string | symbol | null
  path: string
  fullPath: string
}): string {
  return route.name === 'mcp-client-grants' ? route.path : route.fullPath
}
