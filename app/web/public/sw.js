/* Matrix PRP Push worker. Do NOT cache private API responses or JWTs. */
const notificationUrl = () => new URL('notifications', self.registration.scope)

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()))
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()))
self.addEventListener('push', event => {
  let message = { title: 'Matrix PRP', body: '你有一条新提醒', url: notificationUrl().pathname }
  try { if (event.data) message = { ...message, ...event.data.json() } } catch (_) {}
  const rawPath = typeof message.url === 'string' ? message.url : ''
  // Older backend versions send /notifications without the installed application's prefix.
  let target
  try { target = rawPath === '/notifications' ? notificationUrl() : new URL(rawPath || notificationUrl().pathname, self.location.origin) }
  catch (_) { target = notificationUrl() }
  const scope = new URL(self.registration.scope)
  if (target.origin !== scope.origin || !target.pathname.startsWith(scope.pathname)) target = notificationUrl()
  event.waitUntil(self.registration.showNotification(String(message.title).slice(0,120), {
    body: String(message.body).slice(0,500),
    icon: new URL('icon.svg', self.registration.scope).pathname,
    badge: new URL('icon.svg', self.registration.scope).pathname,
    data: { url: target.href },
    tag: 'prp-notification-' + Date.now(),
  }))
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  const scope = new URL(self.registration.scope)
  let target
  try { target = new URL(event.notification.data?.url || notificationUrl().href, scope) }
  catch (_) { target = notificationUrl() }
  if (target.origin !== scope.origin || !target.pathname.startsWith(scope.pathname)) target = notificationUrl()
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async windows => {
    for (const client of windows) {
      if (client.url.startsWith(self.registration.scope) && 'focus' in client) {
        if ('navigate' in client) await client.navigate(target.href)
        return client.focus()
      }
    }
    return self.clients.openWindow(target.href)
  }))
})
