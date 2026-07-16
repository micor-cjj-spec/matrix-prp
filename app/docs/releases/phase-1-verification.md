# Phase 1 Verification Status

Date: 2026-07-15

## Current Gate

The local integrated verification gate passes:

```powershell
.\app\scripts\verify.ps1
```

Verified scope:

- Backend tests: `16 tests, 0 failures`
- Web: TypeScript build and Vite production build
- Mobile: `vue-tsc --noEmit` and uni-app H5 build
- CLI: TypeScript build

## Implemented Phase 1 Capabilities

- Auth: password login, JWT persistence for Web/Mobile/CLI, protected business APIs.
- Dashboard: daily summary, task counts, recent records, finance monthly metrics, runtime health signals.
- Records: create, list, update, delete, filter by module, tag, date, and keyword.
- Tags: create, list, update, delete, and bind to records.
- Tasks: create, list, update, delete, status change, priority and due-date filters, summary metrics.
- Finance transactions: create, list, update, delete, month/type/category filters, monthly summary, category summary, account summary.
- Finance accounts: create, list, update, delete through backend, Web, and CLI; Mobile quick capture can select configured accounts.
- Finance categories: create, list, update, delete through backend, Web, and CLI; Mobile quick capture can select configured income/expense categories.
- Reviews: create, list, update, delete, filter by type/module/period, validation for review type and period range.
- Knowledge: tree, file read, search, stats, and path escape protection.
- Web: login, dashboard, records, tags, tasks, finance, reviews, and knowledge pages.
- Mobile: login, today view, quick record, quick task, quick finance capture, finance summary.
- CLI: login/config/me/dashboard, module, tag, knowledge, record, task, finance, review commands.

## Runtime Checks Still Dependent On Local Services

Full API smoke with MySQL requires Docker Desktop and the `matrix-prp-mysql` container:

```powershell
.\app\scripts\check-env.ps1
.\app\scripts\start-infra.ps1
.\app\scripts\start-backend.ps1
.\app\scripts\smoke-api.ps1
```

`check-env.ps1` verifies local commands, Docker daemon status, MySQL container health when Docker is available, backend/web port usage, and required project paths.

The API smoke script checks:

- Health and runtime health against MySQL.
- Login, current user, dashboard, task summary, finance account summary, knowledge stats, and feature modules.
- Finance account create/list/update/delete using temporary smoke data.
- Finance category create/list/update/delete using temporary smoke data.

Current backend runtime behavior when MySQL is not available:

- `/api/health` starts normally.
- `/api/health/runtime` returns quickly with `status=DEGRADED` and `database=DOWN`.

## Known Warnings

- Web routes are lazy-loaded and vendor dependencies are split. The remaining large chunk warning is the Element Plus vendor bundle, which is acceptable for Phase 1.
- Rollup removes two upstream `/* #__PURE__ */` comments from `@vueuse/core`; this is a dependency warning, not a build failure.
- Backend tests print Mockito dynamic-agent warnings on the current JDK. This is not a test failure, but the build should eventually configure Mockito as a Java agent.

## Next Recommended Work

- Run `smoke-api.ps1` after Docker Desktop is available.
- Add a short release note once runtime smoke passes against MySQL.
- Consider on-demand Element Plus imports before a public release package if first-load size becomes important.
