/* Matrix PRP Push worker. Do NOT cache private API responses or JWTs. */
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()))
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()))
self.addEventListener('push', event => {
  let message = { title: 'Matrix PRP', body: '你有一条新提醒', url: '/notifications' }
  try { if (event.data) message = { ...message, ...event.data.json() } } catch (_) {}
  const url = typeof message.url === 'string' && message.url.startsWith('/') && !message.url.startsWith('//')
    ? message.url : '/notifications'
  event.waitUntil(self.registration.showNotification(String(message.title).slice(0,120), {
    body: String(message.body).slice(0,500),
    icon: '/icon.svg', badge: '/icon.svg', data: { url },
    tag: 'prp-notification-' + Date.now(),
  }))
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  const path = event.notification.data?.url || '/notifications'
  const target = new URL(path, self.location.origin)
  if (target.origin !== self.location.origin) return
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async windows => {
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin) && 'focus' in client) {
        if ('navigate' in client) await client.navigate(target.href)
        return client.focus()
      }
    }
    return self.clients.openWindow(target.href)
  }))
})

