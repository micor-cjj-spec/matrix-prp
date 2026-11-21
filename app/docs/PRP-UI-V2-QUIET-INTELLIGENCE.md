# PRP UI V2 — Quiet Intelligence (静奢智能)

## Invariants
- **4 first-level destinations unchanged**: 首页 `/`、应用 `/apps`、聊天 `/chat`、我的 `/me`.
- **Apps retains registered domain/feature hierarchy**. `appCatalog.ts` and generated feature registry are untouched; search, filters and favorites remain.
- **No feature removal**: route map, API modules, business forms, dialogs, AI consent, write approvals, admin gates, notification actions, chat streaming, history controls remain untouched.
- **No deployment or production schema changes**. This is an isolated feature branch and draft review.

## Implemented
1. Added a single additive `quiet-intelligence-v2.css` imported after the existing `main.css` to govern palette, typography, elevation, states, page grid, responsive breakpoints, mobile bottom navigation and global Element Plus controls.
2. Homepage gets a responsive daily-focus hero with existing task content and direct links to Task, Chat, Wellness, Video while preserving all original metric cards, task controls, domain cards, and quick actions.
3. Wellness gets an overview summary for **selected date** and native existing quick actions (AI record, meal, exercise, body metrics). Six existing tabs remain; no nutrition data is invented or treated as zero.
4. Learning adds the course→practice→notes→review quick path while preserving original video / practice / vocal / notes / admin-only knowledge features.
5. Apps now displays the existing registered modules in the original five category groups (学习/健康/生活/财务/更多工具); it preserves dynamic entries, search, category filters and per-user favorites. Chat, Me and other registered modules retain their scripts and share the visual theme.
6. Existing `app/mobile` uni-app palette aligned, without editing page map.
7. The web build now runs `ui-v2-feature-preservation.test.mjs` in addition to the existing four-tab contract test.

## Not done
- Not merged to main or deployed.
- Visual QA against live authenticated data and physical iPhone is still needed.
- Does not change authorization, database, MCP, backend or feature availability.

## Review checklist
- [ ] Web build + TypeScript checks pass.
- [ ] `four-tab-navigation` and `ui-v2-feature-preservation` tests pass.
- [ ] Login, home, apps, chat, me, module routes at 390px/768px/desktop.
- [ ] Health AI/diet/exercise/metric/goal and edit/delete/copy workflows.
- [ ] Chat iOS keyboard, bottom tab interaction, consent and history.
- [ ] Admin-only features remain subject to original authorization.
- [ ] No functional regressions; no production release without explicit approval.


## 2026-11-21 UI acceptance update
- Apps is now grouped by `groupOrder` and `filtered` instead of a single ungrouped grid. Grouped rendering never changes `getAppEntries`, feature visibility, the favorite key or application routes.
- Accessible secondary text has been darkened (typical contrast approximately 5.2:1–5.8:1 for the evaluated surfaces); direct browser audits remain required.
- Existing four-tab layout, health tabs and backend interaction code have not been removed or replaced.
- Source-level regression tests have been extended to check the grouped app list, mobile chat viewport and category/favorites behavior.
- GitHub Actions CI jobs were still queued when this update was prepared. Do not describe queued/pending jobs as passed.
- The repository currently has no `dev` branch. PR #229 remains a **Draft** against `main` for review only; **do not merge it into main**. If enforcing the user's dev→main policy, establish the designated integration branch through a separate reviewed governance step, then retarget this PR. No production publication is authorized.
