# PRP isolated frontend regression tests

This test package is intentionally independent of `app/web/package-lock.json`.
It never uses the production PRP host, production API credentials or real user data.

## Local setup

```sh
cd app/web && npm ci
cd ../test-automation && npm ci
npm run test:unit
npx playwright install chromium
npm run test:e2e
```

Playwright launches the local Vite dev server at `127.0.0.1:4173` and mocks `/api/**` with synthetic responses before the browser navigates. Do **not** point this test suite at micor.top or production.

Vitest currently protects session restoration, offline-versus-expired tokens and 3 MB food-photo boundaries. E2E tests cover unauthenticated redirects, mocked login return path and rejecting nonadmin navigation.

A CI run must use the committed `package-lock.json` with `npm ci`, never an unlocked install. Add browser tests only with isolated fixtures and no production-mutation endpoints.
