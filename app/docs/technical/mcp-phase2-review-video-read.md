# MCP Phase 2 — Review and video learning read-only (Phase 1, review-only)

Tracking: #218 (child of #170). This branch does not add live MCP tools. No deployment, no production grant, no OAuth/Keycloak change.

## Existing data sources

- Review: `ReviewService.listLimited(ReviewFilter, limit)` calls the existing `MyBatisReviewRepository` owner-scoped filter and enforces an SQL `LIMIT` (1–20). The bounded SELECT fetches only ID, type, module, title, summary, date range and creation time, excluding full highlights/problems/nextActions at the SQL layer. Original `list` behavior for REST is unchanged.
- Video: new `VideoLibraryService.foldersLimited(limit)` and `videosLimited(folderId, limit)` use `CurrentUser.id()`, bind a parameterized SQL `LIMIT`, and reject foreign folders. Original REST methods are unchanged.
- Reuse those services; do not query other tenants, accept a caller-provided userId, fetch playback URLs, issue media tickets, read raw MP4 data, or expose uploading state.

## Phase 1 implementation — deliberately not enumerable by MCP

`McpReviewVideoReadAdapter` provides three narrowly projected read operations:

| Future tool (proposed only) | Candidate method | Response bound | Returned fields |
| --- | --- | --- | --- |
| `prp_reviews_list` | `listReviewPreviews` | 1–20; default 10 | id, reviewType, moduleCode, title (120 code points), summaryExcerpt (200), periodStart, periodEnd |
| `prp_video_folders` | `listFolderPreviews` | 1–50; default 20 | id, parentId, folder name (120) |
| `prp_video_progress` | `listVideoPreviews` | 1–30; default 20 | video id, folderId, title (160), positionSeconds, durationSeconds |

The adapter is a plain Java class, not a Spring component, and has no `@McpTool` registration. Neither `PrpMcpTools` nor `McpToolConfiguration` is changed. Therefore it is **not active** in either test or production and adds **zero** scopes or tools to any existing OAuth manifest.

Review contents such as highlights, problems and next actions are intentionally excluded; summary is truncated. Video storage keys, sizes, upload sessions, raw media, stream URLs and signed playback tickets are excluded. A zero duration remains an unknown duration, not a false assertion that a video was finished. The existing service's owner and folder checks remain required.

## Before Phase 2 integration (explicit separate review)

1. **Implemented in this Draft PR:** SQL-side bounded review query and parameterized video listing. **Added but not yet verified by completed CI:** disposable MySQL 8.4 owner-isolation, overlap/date filtering, soft-delete, row caps, foreign-folder and progress test (`ReviewVideoReadDatabaseIT`). Review query plans/indexes and final test results remain acceptance blockers.
2. Introduce **separate**, explicitly approved `prp.reviews.read` and `prp.video.read` scopes, and keep them disabled by default. Align the authoritative scope catalog, OAuth resource metadata, owner-client grants, expanded account allowlist, tool manifest, optional-read gate, and any production allowlist in one reviewed integration change. Do not borrow write or finance scopes.
3. Register three read-only MCP tools with `readOnlyHint=true`, a fixed per-tool scope, server-side principal recovery, no owner ID arguments, and strict limits. Keep the currently published health nine-tool manifest unchanged.
4. Run disposable synthetic OAuth `tools/list` + `tools/call` coverage: unauthorized / unknown client / revoked grant / missing scope / cross-owner data / wrong folder / expired consent / no video ticket / input caps / response truncation. The new disposable MySQL test must pass on the exact PR SHA; retain separate actual OAuth negative tests.
5. Verify the current `main` CI and migrate/merge only with independent task integration review. A passing unit suite or Draft PR is not a production activation, OAuth approval, or authorization to merge/deploy.

## Synthetic unit tests and disposable MySQL acceptance

Run in `app/backend`:

```bash
mvn -Dtest=McpReviewVideoReadAdapterTests,McpReviewVideoSqlBoundaryTests test
```

Synthetic tests verify projections, filters, bounds and SQL owner predicates. A separate `ReviewVideoReadDatabaseIT` performs real MySQL two-owner checks and runs within the existing CI `video-db-integration` job. **Commitment to run is not a test pass**; inspect the exact CI run before concluding. OAuth E2E remains a separate requirement.

Disposable database test (requires the existing CI-provisioned MySQL 8.4 and `video-integration` profile):

```bash
cd app/backend
./mvnw -B -Dtest=ReviewVideoReadDatabaseIT test
```
