# Review/video MCP tool registration: opt-in gates (Draft #224)

Tracking: #218, #170. This document is **not** an approval to enable or deploy a new capability.

## Dependency

Draft PR #219 owns the bounded read adapter, new owner-scoped SQL `LIMIT` paths, and baseline tests. Draft PR #224 is stacked on that exact branch and must not be merged alone; CI-only Draft PR #225 targets `main` **only to run checks** and must never be merged.

## Proposed read-only capabilities

| Tool | Required exact scope | Default exposed? | Bound | Side effects |
| --- | --- | --- | --- | --- |
| `prp_reviews_list` | `prp.reviews.read` | No | at most 20 owner-scoped summary previews | None |
| `prp_video_folders` | `prp.video.read` | No | at most 50 owner-scoped folder previews | None |
| `prp_video_progress` | `prp.video.read` | No | at most 30 owner-scoped video metadata/progress previews | None |

Scope discovery is a catalog, not authorization. The `additional-read-tools-enabled` flag defaults false and is an additional tool-visibility gate. Even when that flag is true, a tool needs the corresponding explicitly advertised scope; each request still requires verified issuer/resource-bound OAuth identity, linked PRP owner, current token scope, current owner-client grant, and the existing expanded-account/client allowlist.

The currently reviewed `production-wellness-only` production guard continues to reject both new scopes (including the old task/record/practice read extension configuration). **Do not add these scopes to production health consent allowlists** in this task.

## Sensitive data excluded

- Review: highlights, problems, nextActions, full summary after preview cap, entire private note bodies.
- Video: original binary, upload session, storage key, stream URL, media ticket, media auth headers or signed playback response.
- No caller-specified owner/user ID or cross-tenant selectors.
- No write/deletion/approval method exposed.

## Required independent acceptance before activation

1. Both PR heads are explicitly pinned and checked for exact branch ancestry and file scope; #225 is CI-only.
2. All required feature-impact/backend tests pass **on exact SHA** (not merely on an earlier commit).
3. Real isolated MySQL tests verify query limits, owner isolation, foreign-folder rejection, deleted review visibility, stable order, and no unbounded ORM SELECT.
4. Synthetic OAuth MockMvc tests verify read-only `tools/list` and `tools/call`, missing/revoked scope/owner grants, client identity restriction, and separate read-only hints. New `McpReviewVideoOwnedMysqlOAuthIT` runs against disposable MySQL 8.4 with **real PRP client grants, identity-link rows, SQL reads and MCP HTTP dispatch** for two synthetic owners, including owner revocation and missing token scope. The signed JWT decoder is deliberately mocked in that test: it does not replace independent cryptographic issuer/PKCE/Keycloak E2E, which remains required.
5. Confirm production health-only start/consent rejects both new scopes and the preexisting nine-tool visibility remains unchanged.
6. Any activation in testing or production requires a separate reviewed configuration change, human approval, rollback and live acceptance; no automatic deploy or direct `main` push.

## Smoke commands (non-production)

```bash
cd app/backend
./mvnw -B -Dtest=McpReviewVideoReadAdapterTests,McpReviewVideoSqlBoundaryTests,McpReviewVideoOAuthTests,McpOAuthToolManifestTests test
cd ../web
node --test scripts/mcp-scopes.test.mjs
```

These tests use synthetic identities and mocks for several boundaries. They are necessary, not sufficient, for real OAuth, MySQL and production readiness.

Real MySQL + mocked-issuer HTTP acceptance (only inside the existing disposable `video-db-integration` CI job):

```bash
cd app/backend
./mvnw -B -Dtest=ReviewVideoReadDatabaseIT,McpReviewVideoOwnedMysqlOAuthIT test
```

The test creates random synthetic users and records in CI's `matrix_prp` database only. It must never be pointed at production MySQL, production OAuth credentials or real users.
