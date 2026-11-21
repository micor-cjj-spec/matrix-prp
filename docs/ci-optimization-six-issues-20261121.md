# PRP CI six-issue optimization — review only

Scope: GitHub Actions, no merge to `main`, no production deployment.

## Implemented in this draft

1. **Release dispatch**: `Deploy PRP` listens only to `main` branch CI completions. Existing checks for successful push CI, same repository, release-control hold, protected environment and safe rollback remain unchanged.
2. **PR concurrency**: the `CI` and `Feature Impact Report` workflows independently supersede older runs for the same PR. Main push CI and different PRs do not cancel each other. Inner reusable workflow concurrency groups must also be checked before broadening this policy.
3. **CI levels**: L1 includes existing required job statuses `backend-tests`, `web-build`, `mobile-build`, `db-migration-integration`, `video-db-integration`, and `impact-report`. L2 includes existing MCP/OAuth/Keycloak/DB/Chromium suites and remains fail-closed. L3 is the existing production release, backup and restricted SSH gate. Do not yet add path-based skipping: `app/deploy/test_mainline_mcp_ci.py` forbids making reviewed integrations optional, and the `protect-main` ruleset requires stable check names. Any future splitting must preserve statuses and prove impact classification coverage.
4. **Infrastructure diagnostics**: Maven Wrapper 3.9.16 now uses the official Apache binary distribution endpoint, rather than the previously failing Maven Central URL. Keycloak/PRP readiness errors report a bounded HTTP status; the E2E failure handler also probes the fixed synthetic OIDC endpoint through HTTPS Nginx and direct loopback, then prints disposable container lifecycle state. It never exports response bodies, secrets or raw container logs.
5. **Test reuse**: the repeated disposable OAuth E2E tests are intentionally retained because they cover different authorization modes. A later integration PR should refactor their shared startup fixture, with parity tests for readonly, CRUD, first-party, exact-client and Chromium.
6. **Legacy triggers**: legacy branch-specific workflows stay intact until their PR dependencies and runner contracts are mapped. Convert to reusable or manual-only after review; do not delete coverage by filename alone.

## Required follow-up before merge

- Prove the official Apache Maven URL works on an actual GitHub runner, and if it fails restore an explicitly verified distributor with checksum validation.
- Verify Keycloak readiness reports enough cause without printing credentials, auth codes or token payloads; fix any actual health/import fault rather than merely increasing timeouts.
- The failure `New REST route lacks MCP decision: GET /api/memory/history/normal` is on a different feature PR. Add an explicit owner-reviewed map/exclusion *on that feature branch*, not here where the endpoint does not exist.
- Audit current branch protection contexts (required `backend-tests`, `web-build`, `mobile-build`, `db-migration-integration`, `video-db-integration`, `impact-report`) before introducing optional jobs.
- Do not enable `workflow_dispatch` release actions as part of this PR. No merges, deployments or production resources.

## Second review iteration

- Add per-PR concurrency to required `impact-report`; its job name and checks stay unchanged.
- In the disposable Keycloak failure trap, probe HTTPS and direct loopback discovery status codes separately. HTTP `000` denotes an unreachable endpoint. This is diagnostic instrumentation, not a root-cause fix or a production probe.
- Queue backlog is separately tracked in Issue #247; temporary Keycloak readiness failures in Issue #212. Runner scheduling and Keycloak boot remain unverified until this PR's new CI runs actually start.
