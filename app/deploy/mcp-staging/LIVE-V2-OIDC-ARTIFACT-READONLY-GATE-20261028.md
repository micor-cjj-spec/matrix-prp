# Running V2 first-party OIDC artifact inspection — review only, 2026-10-28

> **Not a deploy, install, migration or release approval.**
> This provides a repeatable read-only, source-bound, redacted status
> check for the exact two currently running V2 containers, intended
> before and after **a separately approved** artifact upgrade.

## Known operator evidence before this verifier

Prior operator checks found **absent** in the running
`prp-mcp-v2-gateway-1` Vue JavaScript the three necessary markers
`/me/mcp-link/callback`, `/mcp/identity/oidc/start` and
`/mcp/identity/oidc/finish`. A previous read-only check of the
running `prp-mcp-v2-backend-1` JAR also found no
`McpFirstPartyOidcLinkController.class` or
`McpFirstPartyOidcLinkService.class`.

This evidence establishes that the running V2 images at that time
**predate the PR #113 identity-link implementation**. A `200`
HTML response to the callback URL alone is not sufficient: a
generic SPA fallback can return `200` when the actual JS callback
handler and backend APIs are absent. There is no reason to attempt
real ChatGPT OAuth on that V2 build.

## Actual operator V2 container status — 2026-10-28, definitive missing artifacts

The operator executed the **immutable Git source**
`4d6fba554aa87f83ac5ccd77c07cb76252b16133` from
`app/deploy/mcp-staging/live_v2_artifact_readonly.py` directly using
`git show ... | python3 -B -`, without checkout or deployment.
The complete sanitized stdout is:

```json
{
  "artifacts_feature_ready": "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE",
  "backend_oidc": "ABSENT",
  "backend_running": "YES",
  "docker_state_changed": false,
  "g0_b2_install_permitted": false,
  "gateway_oidc": "ABSENT",
  "gateway_running": "YES",
  "live_oidc_flow_verified": false,
  "purpose": "RUNNING_V2_OIDC_ARTIFACTS_READ_ONLY"
}
```

The operator's outer shell reached `READ_ONLY_COMPLETE`. Both
**real running** V2 containers were read, not merely Git source, and
neither has the required frontend OIDC link route markers nor the
backend controller/service/V28 runtime archive entries. This
**confirms**, rather than only suspects, that the currently deployed
V2 is an older, non-linkable build.

**Hard stop:** An active Keycloak two-client registration alone could
not enable genuine first-party linking on this V2 build. Do not
redirect its browser callback, expose new link endpoints, attempt
ChatGPT connection, or run an unreviewed V28 backend against this
existing V2 database. The correct next review is the **real owner-data
target and a data-preserving release path**, followed by independently
approved image/DB/router cutover, not another Keycloak recovery loop.

There is no new host or Docker mutation and no G0/B2 approval. This
does not prove the correct new backend would work in production
without proper migration and owner linking.

## New metadata-only verification tool

`live_v2_artifact_readonly.py` accepts **no CLI paths or target
container arguments** and queries only:

- Docker status for exact containers `prp-mcp-v2-gateway-1` and
  `prp-mcp-v2-backend-1`.
- Read-only `docker cp ... -` tar streams of fixed
  `/usr/share/nginx/html/assets` and `/opt/prp/app.jar`.
- Presence of the three Vue strings above and three backend runtime
  JAR entries: OIDC Controller, OIDC Service and V28 migration SQL.

It emits a bounded JSON report with
`gateway_oidc`/`backend_oidc` values `ABSENT`,
`PARTIAL_MARKERS`, `ALL_PRESENT` or `UNVERIFIED`, plus a
fail-closed `artifacts_feature_ready` label. It does **not**
print JavaScript, JAR content, file names, user data, Docker environment,
auth headers, tokens, or credentials. It does not write files,
run containers, modify the database or access a network URL. It uses
bounded input sizes and refuses unknown Docker paths.

The script is safe to invoke **only by an authorized operator**
from a pinned source commit. For example, after independently
confirming the current reviewed commit:

```sh
V2=/root/matrix-prp-mcp-v2-staging
PIN=REPLACE_WITH_APPROVED_FULL_GIT_COMMIT
FILE=app/deploy/mcp-staging/live_v2_artifact_readonly.py
git -C "$V2" cat-file -e "$PIN:$FILE"
git -C "$V2" show "$PIN:$FILE" | python3 -B -
```

The above is a **read-only observation**. The script cannot indicate
that the class was exercised, that Spring registration succeeded,
that the Vue login is reachable in real Safari/Chromium, that Keycloak
is configured, or that permissions are correct.
`SOURCE_MARKERS_PRESENT_REVIEW_ONLY` merely warrants
further independently authorized runtime integration tests.

## Minimum actual release sequence

1. Technical recovered-current-Keycloak snapshot result has passed
   (101 tables, 13 clients, exact two-client private create/rollback,
   issuer public JWKS parity, clone cleanup). Do not repeat without drift.
2. Obtain G0/B2 independent validation and the original authentic
   recovery/installer approvals. No generated JSON/PR comment can
   substitute for the controller's acceptance.
3. Independently reconcile existing V2 database/Flyway lineage,
   production task-data ownership, and an approved build-image
   deployment and rollback to 18082. Do not point a new V28 JAR
   at the old V24-mismatched legacy database or run Flyway against
   production based only on synthetic CI.
4. After authorization, install exact vetted backend/SPA image versions,
   then run this artifact presence check again. Approve exact TLS/public
   first-party Nginx routes only after app/API readiness; do not
   route to the older 18081 or unapproved NewDB 18083.
5. Separately approve/register exactly two Keycloak client IDs with
   proper PKCE/JWKS/consent/audience, preserving the 13 clients,
   and test real ChatGPT identity linking and task-only
   `prp_tasks_list` using actual user authorization.

**Never infer release readiness merely from PASS statuses in this
read-only marker inspection.** Existing production PRP V24, active
test Realm, Nginx, V2 Compose local edits and all databases stay
unchanged until the approved transaction.
