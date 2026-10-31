# PRP MCP: PR #95 → #113 → #128 integration conflict review (2026-10-31)

Status: **review only / NO-GO for production**. This is not a merge approval,
Keycloak client registration plan, server runbook, or B2 release evidence.

## Why CI alone does not establish merge readiness

- PR #95 (`feat/prp-mcp-gateway-v1` → `main`) is currently Draft and mergeable.
- PR #113 (`test/mcp-authcode-privatejwt-refresh-20261024` → PR #95 branch)
  is Draft and GitHub currently reports `mergeable_state=dirty`.
- Its recorded base `4f50a0860f65dee3915d25b79ea5ff26c0a4b1ed` is 97 commits
  behind the observed PR #95 head `65687ebf8ffe26ef41995487a9ecfab4d066cf91`.
- PR #128 is a Draft child of PR #113 with green synthetic migration, OAuth
  task-read and password-approved write E2E, but it does **not** resolve the
  parent PR #113's Git merge conflicts.

The two sides both touch 15 paths, as identified by the GitHub compare API.
Treat overlaps as an audit **superset**, not a list of proven line-level conflicts.
The highest-risk overlap areas include:

| Component | Upstream PR #95 behavior | PR #113 / #128 integration issue |
| --- | --- | --- |
| `McpOAuthResourceServerConfig.java` | Reject access tokens whose `aud` includes unrelated APIs | PR #113 had reverted to simple `contains(resource)`. Restored strict allowlist in PR #128; retain exact `/api/mcp` raw-path validation from PR #113. |
| `McpClientGrantService.java` and `McpClientGrantController.java` | Ten-minute browser-pairing lease, SQL-clock expiry, explicit user consent | PR #113 inherited pre-lease service despite PR #95 adding the lease. Restored upstream service/controller and real-MySQL regression in PR #128. |
| `V28` migrations | `V28__mcp_temporary_client_grant_expiry.sql` creates the lease table | PR #113 had reused V28 for OIDC link flows. PR #128 preserves V28 and moves OIDC to V29; **do not reuse or edit installed migration versions**. |
| `app/web/src/views/McpClientsView.vue`, `app/web/src/router/index.ts` | Time-limited browser pairing UI and safe unauthenticated redirect helper | PR #113 adds first-party OIDC link UI/callback. Both flows must be reconciled rather than selecting an older file wholesale or dropping the safe-redirect rule. |
| `app/deploy/mcp-oauth/test_full_e2e_ci.sh` | Browser-pairing and source feature assertions | PR #113 adds first-party identity linking and exact ChatGPT client-ID simulated auth. Preserve both security tests where applicable; PR #128 corrects V29 JAR migration assertion. |
| Nginx/staging/Keycloak diagnostics | Existing staging routing and browser-pairing gates | Diff and test concrete edge paths before accepting a combined staging artifact; do not alter live Nginx or Realm policies as a conflict workaround. |

Other shared paths that need normal three-way comparison before merging:
`.github/workflows/mcp-oauth-keycloak-smoke.yml`,
`app/deploy/mcp-oauth/chatgpt-cimd-repair.md`,
`ci_chatgpt_cimd_pkce.py`,
`ci_jwt_authcode_refresh.py`,
`public_route_preflight.py`,
`test_public_route_preflight.py`,
`app/deploy/mcp-staging/README.md`,
`approval-routes.pending.md`,
`approval_routes_pending.py`,
`compose.yaml`, and `test_staging_config.py`.

## Required integration sequence (all on disposable/review branches)

1. Preserve and confirm the upstream OAuth audience allowlist and pairing
   lease enforcement, including negative audience tests, true SQL expiry,
   owner separation and revocation. Do not accept a downgrade.
2. Resolve the PR #113 merge conflicts against PR #95 through an independently
   reviewed three-way merge. Preserve safe unauthenticated Vue redirect,
   browser-pairing scopes, first-party OIDC callback, and explicit separate
   ChatGPT client account consent; review every overlapping UI/route file.
3. Enforce immutable migration lineage V25–V29 and verify old V7 baseline/V24
   data. Do not infer live Flyway history from disposable CI.
4. Rebuild *one exact candidate* Java JAR and Vue bundle from the reconciled
   commit. Verify V28 pairing lease and V29 OIDC migration **both** exist and
   first-party controllers and Vue callback routes are present.
5. Run isolated Keycloak/MySQL, exact-ID synthetic signing OAuth task read,
   Chromium first-party callback, full approval-gated draft write, expiry and
   revoke regressions on that same reconciled commit.
6. Independently review live deployment B2 evidence, exact Realm/policy/client
   inventory and release authorization. Only then consider a separate approved
   create-only client registration and real ChatGPT-signed OAuth flow.

## NO-GO scope

This document does not establish that the live test Realm contains the exact
ChatGPT OAuth client or `prp-first-party-link`, that a real ChatGPT assertion
was verified, that the running V2 images contain the updated JAR/Vue code,
or that production PRP tasks/writes have been accessed. All these remain
unverified until a separate explicitly authorized, independently audited
acceptance process. No live Keycloak, MySQL, Nginx, SSH, or PRP changes here.
