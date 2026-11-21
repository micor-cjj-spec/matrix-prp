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

## Exact-head CI evidence and route capability audit

- Phase 1 Draft #219 at `4b2902f77fc9cf92a88e68cc12594c77c928580b`: [CI #44924661707](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44924661707), attempt 2 **34/34 PASS**.
- Phase 2 combined CI at `58a694a770b01fce92721eefa2caddcf410a7c40`: [CI #44924688689](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/44924688689) **35/35 PASS**, 463/463 backend, 29/29 real MySQL, and real disposable Keycloak RSA-signed two-scope PKCE `review-video` job PASS. These results apply **only to those SHA values**; after any new documentation/contract commit, review the new exact-head checks again.
- Parent Issue #170 additionally requires a REST-to-MCP capability registry update. This Phase 2 records three **partial** mappings: `GET /api/reviews -> prp_reviews_list`, `GET /api/video/folders -> prp_video_folders`, and `GET /api/video/items -> prp_video_progress`. All return narrower, bounded projections than the REST endpoints. Playback, media and upload-state routes remain **excluded**. The mapping catalog is an audit artifact, **not** a tool enablement flag or a user grant.

## Real-client and release decision gate (NO-GO until independently cleared)

The CI-only signed-token test uses disposable Keycloak, synthetic owners and a throwaway private key for the exact ChatGPT client ID. It **does not** prove OpenAI possesses/uses that key or that the active Realm accepts the actual ChatGPT `private_key_jwt` assertion.

Before a separately approved *isolated test-stage* activation, require all of:

1. A newly dated read-only inventory of the target Realm's exact-client policy, profiles, mappers, JWKS trust and existing clients. The October G0/B2 records in `app/deploy/mcp-oauth/keycloak-resource-guard/G0-EXACT-CLIENT-DELTA-REVIEW-20261027.md` and `B2-RELEASE-GATE.md` historically marked installation **NO-GO** and genuine current backup/restore/install approval receipts missing; do not treat these dated observations as proof of today's state or fabricate approval receipts.
2. Explicitly authorized fresh backup plus **isolated restore and rollback evidence** for the actual target Keycloak Realm and signing state; verify original client inventory and exact audience mapper are preserved. Never modify a shared Realm, public Nginx or production database to shortcut a failed gate.
3. Explicit review of real ChatGPT CIMD metadata, exact `https://chatgpt.com/oauth/client.json` client, registered callback, `private_key_jwt`, PKCE S256, exact `resource` and trusted HTTPS discovery. Verify real signed token's audience, issuer, client identity, scope and expiry without exposing credentials, codes, access/refresh tokens, cookies, PKCE verifier or PII in Issues.
4. A separately approved, non-production account linkage and consent test: grant **only** `prp.reviews.read` and/or `prp.video.read` to the intended synthetic/test user; confirm no unrelated reads/writes, foreign account denial, and immediate access revocation. Do not equate this to production consent.
5. A production-specific **new change request and separate rollback review**: the existing `McpProductionWellnessGuard` intentionally rejects both new scopes and existing health-only grants must remain intact. **Do not disable or weaken that guard in #218.**

**Rollback boundary:** in any future separately authorized test-stage activation, first turn OFF `matrix-prp.mcp.additional-read-tools-enabled`, restore the previously approved exact advertised-scope configuration, revoke only the newly granted test client scopes and verify existing task/health tools still work. Restore Keycloak policy/client changes solely through the original approved G0/B2 rollback transaction. Never delete shared Keycloak clients/volumes, rotate production keys casually, or use `docker compose down -v` against a shared environment.

**Decision:** code-level review and disposable CI may be accepted as engineering evidence, but #218 is **not release approved**. Keep #219/#224 Draft, never merge #225, and do not deploy or expand production OAuth consent without a distinct user-authorized change.
