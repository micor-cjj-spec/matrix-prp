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
- The page source and functional regression checks must remain separately accepted on the **exact UI feature head**; a passing CI-only combination is not proof that this original UI PR independently passed every required gate.
- The application catalog defines five *possible* category groups (`learning`, `health`, `life`, `finance`, `other`), but only **nonempty** groups render. `更多工具` is intentionally absent until a registered available module belongs to that group; do not create placeholder features merely to force five visible sections.

## 2026-11-22 GitHub integration / release-gate correction
- The official `dev` integration branch now exists at `3ada1c20d2b9378f8dff6e4bab9c5735d162b8b4`, matching `main` at this verification. `main` was protected; `dev` was **not protected**. Do not mistake branch creation for a protection policy.
- **Original UI V2 source Draft PR #229 now targets `dev`, not `main`.** This is still a Draft, not merged, not in production. All original four destinations and the complete feature registry must remain.
- [Draft #272](https://github.com/micor-cjj-spec/matrix-prp/pull/272) proposes only the existing CI and Feature Impact event filters for `dev`; it was **not merged** and its standalone first-attempt CI did not pass.
- The **CI-only combination** [Draft #274](https://github.com/micor-cjj-spec/matrix-prp/pull/274), exact head `4d9262c781e142dec010343691ec14b23f9cbc59`, passed [30/30 complete CI jobs (attempt 2)](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44970068905) and the [Feature Impact Report](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44970068902). This validates the **five-file integration/test-fixture combination**, not a standalone approval of UI #229 or a release.
- [Draft #280](https://github.com/micor-cjj-spec/matrix-prp/pull/280) adds **synthetic** homepage and complete unfiltered app-directory screenshots to Chromium/WebKit QA; see exact-head results below. Synthetic browser results cannot replace physical iPhone Safari/PWA testing.
- The enforced `dev → main` PR-source rule, `dev` protection, physical iPhone Safari keyboard/PWA checks, and authorized test-environment business/role/health/AI approval UAT remain **unmet**. See [UI V2 release gate #262](https://github.com/micor-cjj-spec/matrix-prp/issues/262).
- Keep `app/deploy/publication-hold.json` and `main` Ruleset unchanged unless a separate reviewed authorization explicitly approves changes. **No merge to `dev` or `main`, no production deployment or real-user write is authorized by this document.**

## 2026-11-22 Browser acceptance evidence (synthetic data only)
- Source UI Draft [#229](https://github.com/micor-cjj-spec/matrix-prp/pull/229) and visual-test Draft [#280](https://github.com/micor-cjj-spec/matrix-prp/pull/280) have **identical Git blob SHA for 14/14 compared UI/test files**, including the four first-level tabs/layout, Home, Apps, Wellness, Learning, both V2 CSS themes, the Web bootstrap, mobile Video/AI, native page registry, and source-preservation tests. The documentation-only PR #229 update does not affect these files.
- [Chromium and WebKit browser run #44971610660](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44971610660) at visual-test head `5e5d033487f4aba5df614fb48a4b4abe88086031`: **COMPLETED/SUCCESS, both browsers passed**. Each archived 17 synthetic PNG screenshots covering viewport widths 1280px, 768px, 390px: home, all unfiltered app groups, filtered app directory, chat composer, emulated mobile keyboard geometry, and wellness.
- The [Feature Impact Report #44971610618](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44971610618) at the same visual-test head is **COMPLETED/SUCCESS**.
- [Full CI #44971610629](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44971610629) on the same visual-test head passed **29/30 jobs in attempt 1**, with one failed Maven-wrapper download of `apache-maven-3.9.16-bin.zip` before Flyway assertions. An unchanged-code **failed-jobs-only attempt 2** was accepted but **queued at the evidence checkpoint**. Do not mark this workflow green until its completed result is confirmed.
- The synthetic non-admin app directory has 11 available entries in four nonempty groups (学习 4, 健康 1, 生活 5, 财务 1); the fifth defined category, 更多工具, is empty and correctly hidden. No user-specific or production data was used.
- **Still required:** a physical iPhone Safari keyboard/focus/PWA test, real authenticated staging workflows (role visibility; health AI/meal/exercise/metric/goal including edit/delete; chat streaming/consent and owner approvals), dev protection, enforced dev-only PR source to main, and distinct reviewed integration permission. The tested screenshots are not production sign-off.
