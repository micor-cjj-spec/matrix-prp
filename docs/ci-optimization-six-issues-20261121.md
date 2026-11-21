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

## PKCE failure diagnosis (2026-11-21 15:14 UTC)

On PR #249 SHA `cb2a2a0`, all 32 other main CI jobs passed. Two real PKCE E2E matrix jobs failed after 150 seconds with `Keycloak (last HTTP status: unreachable)`, while independent curl probes returned HTTP 200 for *both* fixed synthetic OIDC endpoints: direct `127.0.0.1:18080` and `https://auth-e2e.localhost` via Nginx. Keycloak/Nginx/MySQL containers were running, exit code 0, OOM false. This strongly implicates Python urllib's automatic hosted-runner proxy configuration rather than Keycloak availability. The Python opener now explicitly uses `ProxyHandler({})` to force local HTTP(S) calls to stay local while retaining TLS validation, cookies and restrictive OAuth redirects. A contract regression locks in that behavior. The fix still requires real CI proof; it is not a reason to waive PKCE tests.

## Root cause reproduction and fail-closed certificate repair

On the exact previous SHA `fc3fae4`, both PKCE E2Es still failed: the Python client reported an unreachable Keycloak while the independent curl probes got HTTP 200 for direct loopback and HTTPS Nginx. An isolated replication of the CA/leaf OpenSSL commands demonstrated that Python 3.13 strict certificate verification rejects the generated CA with `certificate verify failed: CA cert does not include key usage extension`, even while curl returns 200. Adding CA `basicConstraints=critical,CA:TRUE` and `keyUsage=critical,keyCertSign,cRLSign` makes `openssl verify -x509_strict` and strict Python HTTPS verification succeed in that reproduction. The CI E2E now includes the explicit extensions and strict chain check before boot; TLS validation is not disabled. This root cause must still be confirmed by the next GitHub CI run.
