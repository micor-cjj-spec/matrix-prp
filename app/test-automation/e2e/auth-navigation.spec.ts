import { expect, test, type Page } from '@playwright/test'

const profile = {
  id: 99001, username: 'fixture', displayName: 'Fixture Tester', administrator: false,
}

async function stubBackend(page: Page) {
  await page.route('**/api/**', async route => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (pathname === '/api/auth/login' && request.method() === 'POST') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'OK', message: 'success',
          data: { token: 'synthetic-local-test-token', tokenType: 'Bearer', expiresInSeconds: 900, user: profile },
        }),
      })
    }
    if (pathname === '/api/users/me') {
      return route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ code: 'OK', message: 'success', data: profile }),
      })
    }
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 'OK', message: 'success', data: [] }),
    })
  })
}

test('unauthenticated private navigation redirects to login without touching production', async ({ page }) => {
  await stubBackend(page)
  await page.goto('/finance')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await expect(page.locator('input[autocomplete="username"]')).toBeVisible()
  await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible()
})

test('mocked login returns to the requested private route', async ({ page }) => {
  await stubBackend(page)
  await page.goto('/finance')
  await page.locator('input[autocomplete="username"]').fill('fixture')
  await page.locator('input[autocomplete="current-password"]').fill('synthetic-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/finance$/)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('matrix-prp-token')))
    .toBe('synthetic-local-test-token')
})

test('a non-administrator cannot navigate to the agent workspace', async ({ page }) => {
  await stubBackend(page)
  await page.addInitScript(() => localStorage.setItem('matrix-prp-token', 'synthetic-local-test-token'))
  await page.goto('/me/agent-tasks')
  await expect(page).toHaveURL(/\/me$/)
})
