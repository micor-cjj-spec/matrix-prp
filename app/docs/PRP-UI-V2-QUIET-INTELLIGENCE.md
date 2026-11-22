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

## 2026-11-22 Exact-head CI closeout and release preparation

- Synthetic integrated QA Draft [#280](https://github.com/micor-cjj-spec/matrix-prp/pull/280) exact head `964563417e2cf932074c71630d2f6e4e7a4a7a33`: [Full CI #44976972272](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44976972272) **30/30 completed/success**; [Chromium + WebKit #44976972319](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44976972319) **2/2 completed/success**; [Feature Impact #44976972280](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44976972280) **completed/success**. This **supersedes the intermediate queued/failed state** recorded in the historical checkpoint above. It validates synthetic browser and integrated CI only.
- Original UI source Draft [#229](https://github.com/micor-cjj-spec/matrix-prp/pull/229) remains targeted at `dev` and **has no own CI check runs**. Existing base workflows target `main`; [Draft #272](https://github.com/micor-cjj-spec/matrix-prp/pull/272) and [Draft #274](https://github.com/micor-cjj-spec/matrix-prp/pull/274) propose and exercise `dev` CI integration but remain unmerged. Do not interpret #280's success as independent required checks on #229.
- `main` and `dev` both resolved to `3ada1c20d2b9378f8dff6e4bab9c5735d162b8b4` at this checkpoint. Main has an active PR/check Ruleset, but `dev` is unprotected and no enforced main PR-source policy limits head to the repository's `dev`. [Release gate #262](https://github.com/micor-cjj-spec/matrix-prp/issues/262) remains **NO-GO**.

### Physical iPhone / authorized staging acceptance script (NOT YET EXECUTED)

**Environment prerequisite:** An explicitly authorized isolated test deployment of the actual candidate commit; synthetic non-admin and admin test accounts, seeded per-account tasks/catalog/health/learning data, test-only chat/MCP approval path, and the ability to inspect sanitized server-side result/denial logs. Never use production, real personal health entries, live approvals, live credentials or screenshots containing secrets. If the prerequisite is absent, mark the affected case **BLOCKED**, never PASS.

| Case | Execution on physical iPhone Safari / permitted test environment | Pass criterion |
| --- | --- | --- |
| IOS-01 | Visit home → Apps → Chat → Me, enter a module and return to Apps; repeat on an iPhone with a safe-area inset. | Four top-level destinations remain navigable; active state, back behavior and bottom nav not obscured or replaced. |
| IOS-02 | Chat: focus textarea, raise system keyboard, type a long multiline message, scroll history, hide keyboard, change tabs and return. | Composer/send button visible and tappable, no keyboard overlay/scroll offset leak; tab bar returns when keyboard closes. |
| IOS-03 | On home, app catalog and chat, rotate portrait/landscape, change iOS text size, scroll a long list/dialog. | No clipped critical actions or horizontal overflow; accessible hit targets and safe areas remain usable. |
| IOS-04 | In Safari tab and (where permitted) Add to Home Screen PWA, launch, navigate tabs, background/resume and return. | No blank state, lost navigation, duplicated layout/keyboard or unexpected sign-out. |
| APP-01 | With seeded ordinary-user catalog, test original four nonempty groups, search, category filter, favorite/unfavorite and refresh. | Registered entries/route destinations retained; no synthetic placeholder for an empty category; favorites persist only for owning account. |
| ROLE-01 | Sign in ordinary user then admin; attempt an admin-only screen using both navigation and direct URL/API call. | Admin sees authorized features; ordinary user cannot access them, including server-side authorization denial. |
| TASK-01 | Complete a seeded task from home, refresh and inspect sanitized backend result; retry during slow/failing network. | Exactly one authorized write on success, durable state on refresh; failed/timeout request never displays false success. |
| HEALTH-01 | Visit all six existing health tabs, switch selected day including an empty day, compare summary to seeded records. | All tabs usable; date semantics correct; missing data is not silently fabricated as zero. |
| HEALTH-02 | With synthetic data, add/edit/copy/delete a meal; verify nutrition/selected-date summary; repeat exercise, body metric and goal operations. | Create/update/delete/readback and totals consistent, no duplicates, and all writes restricted to the test account. |
| LEARN-01 | Traverse course/video, practice, notes/review and other authorized learning features; return to Apps. | All originally available entrances/routes preserved; admin-only items follow permission rather than disappearing universally. |
| AI-01 | Test chat stream/history/session switching and an approval flow; explicitly deny and expire one staged write request. | Normal messages persist appropriately; no write without consent; denial/expiry causes no mutation; approval and audit state align. |
| AUTH-01 | Log out, switch from ordinary test user to a separate account, verify Apps favorites, tasks and health isolation; repeat after network interruption. | No cross-account data, stale cached controls or token leakage; session expiry and errors are actionable. |

**Evidence record per case:** `case ID | test environment ID/host | tested Git SHA | device & iOS/Safari versions | test account role (not identifier) | UTC time | PASS/FAIL/BLOCKED | redacted screenshot/video | steps to reproduce | sanitized request/trace ID`. Capture failures as FAIL with reproduction; missing access/device as BLOCKED. Review backend denial and write-result logs without tokens, passwords, names, actual health data, OAuth state/code or unredacted URLs.

**Approval boundary:** Passing this script is still not a merge or release authorization. Separately verify protected `dev`, enforced repository-local `dev → main` PR source gate, source-PR checks, reviewed merge order, backup/rollback evidence and an explicit production release decision. Keep existing production publication hold in force.

### 2026-11-22 03:04 UTC: `dev`-target synthetic QA closed GREEN

- Latest QA [Draft #280](https://github.com/micor-cjj-spec/matrix-prp/pull/280) targets `dev` at exact head `4719baf7b10fc701885979af9ddf95e92b43a739`. [Full CI #44978491486](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44978491486) **30/30 SUCCESS**; [Chromium/WebKit #44978491480](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44978491480) **2/2 SUCCESS**; [Feature Impact #44978491476](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44978491476) **SUCCESS**, all on this same commit. V28→V29 isolated restore assertions completed successfully.
- Independently re-fetched and compared Git blob SHA of the original source PR #229 and this current QA head for **14/14 UI/mobile/preservation-test files: all identical**. The QA-only differences are CI configuration and synthetic test harness; they do not establish native Safari or authenticated acceptance.
- **Source PR #229 has zero standalone GitHub check runs on its own head.** Existing `dev` target filters are still Draft-only, so the source PR itself cannot be called independently CI-approved. Draft #272 (triggers) / #274 (integration checks) / #263 (main source-branch guard) remain separate review proposals.
- **Release gate #262 stays OPEN / NO-GO.** Physical iPhone Safari/PWA, authorized isolated role/health/chat workflow testing, protected `dev`, enforced same-repository `dev→main` source gate, source-head required checks and explicit production approval are still missing. Do not merge or deploy on this evidence alone.
