# Unified Staging read-only API smoke (#396)

Production-equivalent Staging, not the default-off CI sandbox. This operator-run smoke reuses the actual frontend GET endpoint paths in the #403/#404 candidate, not the existing synthetic Playwright intercepts. It is NOT a full UI/UAT check or permission to deploy.

1. Open https://prp-test.micor.top/prp/ with the designated synthetic test account. Stop if it is not a known isolated test identity or unexpected real data appears.
2. Review the exact `unified_staging_read_smoke.cjs` source. Run it as a browser developer-tools snippet on that already logged-in page. Do not disable browser safety warnings or run an unreviewed remote loader. Confirm test identity in the script prompt. No password/token copy, install or server change.
3. Return only the generated JSON: case IDs, status classifications, ordinal checks. No payloads, usernames, tokens or screenshots. API_PASS means a successful HTTP/JSON/envelope/shape check only. UI rendering, two-owner negative tests, actual data correctness, external calls, real iPhone, writes and restore remain separate.

The origin and API paths are fixed, GET only; no redirects, no cookies, no external target, no business writes or provider invocation. Authentication uses the existing local session token in memory, never printed. The first request validates the signed-in profile response; confirmation of synthetic identity is the operator's responsibility. Normal server access logs may be generated. API group failures are not automatically bugs (e.g., 403 may reflect intended role). U04 reads daily/nutrition summaries; U06 checks video folders/practice subjects; U07 goals only; U08 conversation page only, no prompts/messages. A separate scoped approval is required for write/provider/identity isolation tests. No CI or production deployment is added.

Offline unit tests (no network): `node --test app/scripts/unified_staging_read_smoke.test.cjs`.
