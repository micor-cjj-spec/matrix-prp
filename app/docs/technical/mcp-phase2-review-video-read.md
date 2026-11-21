# MCP Phase 2 — Review and video learning read-only (Phase 1, review-only)

Tracking: #218 (child of #170). This branch does not add live MCP tools. No deployment, no production grant, no OAuth/Keycloak change.

## Existing data sources

- Review: `ReviewService.list(ReviewFilter)` calls the existing `MyBatisReviewRepository`, which filters by `CurrentUser.id()` and supports reviewType/moduleCode/period bounds.
- Video: `VideoLibraryService.folders()` and `videos(folderId)` filter by the current owner. The latter validates folder ownership before returning items.
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

1. Add a SQL-side bounded review query (the present response limit is **not** a database query limit); review date filtering/retention as needed. The current video listing likewise fetches all owned rows and caps only the returned response.
2. Introduce **separate**, explicitly approved `prp.reviews.read` and `prp.video.read` scopes, and keep them disabled by default. Align the authoritative scope catalog, OAuth resource metadata, owner-client grants, expanded account allowlist, tool manifest, optional-read gate, and any production allowlist in one reviewed integration change. Do not borrow write or finance scopes.
3. Register three read-only MCP tools with `readOnlyHint=true`, a fixed per-tool scope, server-side principal recovery, no owner ID arguments, and strict limits. Keep the currently published health nine-tool manifest unchanged.
4. Run disposable synthetic OAuth `tools/list` + `tools/call` coverage: unauthorized / unknown client / revoked grant / missing scope / cross-owner data / wrong folder / expired consent / no video ticket / input caps / response truncation. Add actual MySQL tests for the owner-scoped queries and bounded SQL.
5. Verify the current `main` CI and migrate/merge only with independent task integration review. A passing unit suite or Draft PR is not a production activation, OAuth approval, or authorization to merge/deploy.

## Isolated unit test

Run in `app/backend`:

```bash
mvn -Dtest=McpReviewVideoReadAdapterTests test
```

These tests use only synthetic Mockito services and verify projections, filtering, caps, input refusal and lack of playback/write invocation; they do **not** prove actual OAuth or cross-user E2E security.
