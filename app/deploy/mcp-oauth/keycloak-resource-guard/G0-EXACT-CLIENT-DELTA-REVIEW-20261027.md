# G0 exact-client change request — observed test Realm, 2026-10-27

> **Status: READY FOR INDEPENDENT REVIEW; NO-GO FOR INSTALL.**
> This document preserves operator-reported *read-only* facts. It is not
> permission to alter active Keycloak, Nginx, the PRP V2 database, B2, or
> `main`. PR #113 stays Draft; MCP writes remain disabled.

## Exact objective and target

Enable real ChatGPT OAuth to a separate, task-read-only PRP V2 staging
gateway, followed by deliberate owner identity linking, without affecting
the live production PRP site or any existing OAuth client. The test
resource is `https://prp-test.micor.top/api/mcp`, issuer
`https://auth-test.micor.top/realms/prp-mcp`, V2 loopback gateway
`127.0.0.1:18082`. The separate older stage at `18081` is **not**
the intended task-only release target. Its six advertised scopes are not
evidence of task-only behavior. The existing OIDC HTTPS loopback endpoint
is `127.0.0.1:18443`.

## Observed current state — operator terminal outputs

| Check | Observed | Evidence boundary |
| --- | --- | --- |
| Realm `prp-mcp` count | **1** | Live, read-only Keycloak PostgreSQL |
| Existing Realm client count | **13** | A count, not a complete client/policy/mapping backup |
| Client scope `basic` | **PRESENT** | Existence only |
| Client scope `offline_access` | **PRESENT** | Existence only |
| Client scope `prp.tasks.read` | **PRESENT** | Existence only |
| Exact ChatGPT Client ID | **MISSING** | Does not prove native CIMD cannot separately resolve it |
| Exact first-party Client ID | **MISSING** | Cannot run PRP first-party flow as designed |
| V2 resource metadata | 200; scope catalog **only `prp.tasks.read`** | Does not prove client consent, token scope or authenticated task access |
| V2 no-bearer `initialize` | **401**, correct `Bearer resource_metadata` | Correct rejection only; no signed real ChatGPT token |
| OIDC discovery via local 18443 | Expected issuer, auth/token/JWKS URIs | Diagnostic `curl -k` skipped TLS certificate trust validation |
| Nginx current main SHA256 | `ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b` | Only the two inspected files were hashed |
| Nginx current V2 SHA256 | `35bb31322b23efef536c97e12619ceac7087aa4cf2d56c57f3307232f9362397` | Matches known active V2 baseline, **not** approved guard candidate |
| Read-only SQL runner | `COMMIT` and `V2_WORKTREE_COMMIT_UNCHANGED=YES` | No installation or database writes |

The latest operator execution used
`realm_scope_readonly.sql` from the SHA-pinned Draft commit
`48159759227dba4b4206d79bcedb7587ffc57263`.
It did not mutate the Realm, create any clients, grant consent, perform
OAuth sign-in or contact actual ChatGPT.

## Real B2 evidence inventory — 2026-10-27 (operator-reported)

The original `b2_evidence_inventory.py` was read directly from the
SHA-pinned PR #113 commit
`1f6914d9aa52195a9197e3f3d0185accd73485e0`
with `git show`, without modifying the V2 Git worktree. Its reported
**metadata-only** outcome was:

| B2 field | Actual reported value | Correct interpretation |
| --- | --- | --- |
| `host_guard_directory` | `METADATA_OK_UNVERIFIED` | Parent directory metadata acceptable, not signed approval |
| `approved_install` | `MISSING` | No independently issued install/acceptance receipt at its required path |
| `fresh_b2_restore` | `MISSING` | No fresh independently issued recovery/restore receipt |
| `snapshot_dump` | `PRESENT_METADATA_ONLY_UNVERIFIED` | File existence/permissions, **not** verified hash or a fresh restore |
| `operator_restore_test` | `PASSED_SEPARATELY_OPERATOR_REPORTED_NOT_A_B2_RECEIPT` | Historical isolated operator report, not a valid release receipt |
| `b2_authorization` | `BLOCKED_UNTIL_INDEPENDENT_REVIEW` | No permission to alter active Realm or Nginx |
| `deployment_permitted` | `false` | Stop: no deploy, install or silent gate bypass |

**Next real-world dependency:** an authorized independent G0 reviewer
and the designated original recovery/install controllers, not a
re-run of the unchanged inventory. The reviewer first approves a
precisely scoped, reversible proposed transaction. The authorized
recovery process independently verifies/attests a fresh restore and
the original approved installer independently supplies genuine
installation acceptance as defined by its own controller.
Do **not** fabricate, prepopulate, copy or backdate either JSON
receipt; do not edit the controller's expected hashes to force
acceptance. Whether either document is expected before or after
a controlled installation is determined only by the original
versioned release-controller contract, not by this review note.
Until the legitimate process issues/accepts them, B2 stays NO-GO.

## Proposed minimal delta — not an install command

**Only two create-only clients**, as described by
`app/deploy/mcp-oauth/review_exact_client_registrations.py`:
1. `prp-first-party-link`: public Authorization Code + S256,
   exact callback `https://prp-test.micor.top/prp/me/mcp-link/callback`,
   `basic` default, no optional data scopes; no implicit/password/
   service-account grant, no wildcard callback or broad web origins.
2. `https://chatgpt.com/oauth/client.json`: confidential
   `client-jwt` (`private_key_jwt`) with official
   `https://chatgpt.com/oauth/jwks.json`, only
   `https://chatgpt.com/connector_platform_oauth_redirect`,
   S256, required consent, `basic` default; optional
   `prp.tasks.read` plus protocol `offline_access`.
   Fixed audience `https://prp-test.micor.top/api/mcp`.

The existence of these three Client Scope records makes creating new
scope *names* unnecessary **at this moment**, but DOES NOT validate
their protocol mapper/consent/assignment contents. No data Scope for
finance, wellness or MCP writing is proposed. The existing 13 clients,
policies, Realm defaults, user identities and signing keys must stay
unchanged unless separately reviewed. No full Realm import is proposed.

## V2 browser route upstream lineage correction — review-only

Source inspection found that the earlier
`render_readonly_link_routes("/path/to/ca.pem")`
had used the older generic `18443` TLS upstream. In the persistent
OAuth staging Compose, that public-facing private TLS container's
`prp-test.micor.top` host forwards to
`prp-mcp-stage-gateway-1:8080`, which belongs to the **separate**
older `18081` database environment, not the desired V2 `18082`.
This is a real *source-level route lineage error* in the **uninstalled**
review candidate, not evidence that a live misrouting occurred.

The newer Draft branch `render_readonly_link_routes()` pins the
13 precisely named routes plus the assets regex to the observed
`http://127.0.0.1:18082` V2 loopback target and explicitly rejects
alternate `18081` or `18443` choices. Existing, broader
`render_approval_routes` was not modified to target V2 and
**must not** be installed for task-read-only linking. V2 HTTP
loopback requires an already-verified public HTTPS front end;
an internal loopback `200` would not prove public TLS or an
actual built SPA/OIDC feature.

Before any operator change, independently verify the *actual* V2
gateway image and its database association, fixed `/prp/login`,
`/prp/me/mcp-clients`, `/prp/me/mcp-link/callback`,
`/api/mcp/identity/oidc/start` and `finish` routes,
noncanonical path denials, and exact user authorization. Current
deployed V2 may predate the PR #113 browser implementation.
Do not silently swap the old 18443 TLS ingress for V2,
install this candidate, or enable bootstrap until G0/B2 and
a separate browser-route decision are complete.

## 2026-10-27 V2 deployed gateway artifact — new operator evidence

The operator compared the **running** Docker gateway image digests:

- `prp-mcp-v2-gateway-1`: `sha256:446b521960773e4667281d2f80130eb782d10cb9364de0fb75f267bbb379b1a4`
- `prp-mcp-stage-gateway-1`: `sha256:cc2a8a236c37b69c4353adafbd4184996599130a6723ed8d7c4a026f0cb48aa6`

These are different images, but image inequality alone does not
identify their source commit. Three V2 frontend paths
(`/prp/login`, `/prp/me/mcp-clients`,
`/prp/me/mcp-link/callback`) each returned `HTTP 200 text/html`
over the V2 loopback. The Nginx SPA fallback
`try_files ... /prp/index.html` means these responses **do not**
prove all Vue routes are present or functional.

The operator then inspected **only** the running V2 container's
`/usr/share/nginx/html/assets` build files with literal
`grep -rFq` checks; all three markers were `NOT_FOUND`:

- `/me/mcp-link/callback`
- `/mcp/identity/oidc/start`
- `/mcp/identity/oidc/finish`

This is strong evidence that the running V2 Web build predates the
first-party account bootstrap code or otherwise does not contain the
expected visible strings. Bundler rewriting/splitting can invalidate
literal search as absolute proof. **Do not** treat 200 SPA HTML as
a first-party OIDC acceptance.

**Additional check before proposing any V2 artifact migration:**
inspect the running V2 backend JAR *read-only* for the new
`McpFirstPartyOidcLinkController.class` and
`McpFirstPartyOidcLinkService.class` ZIP entry names, and record
only FOUND/NOT_FOUND, not JAR contents, credentials or database records.
An unchanged draft frontend source file is not deployed merely
because its disposable CI passed. A new backend from PR #113
MUST NOT be pointed at the current V2/legacy-stage MySQL: see
`app/docs/technical/mcp-flyway-lineage-reconciliation.md`
for historical V24 migration collision and the requirement
for separately approved, independently restored, isolated
new-schema tests. No backend rebuild, Compose restart,
database repair, production merge or public route change is
permitted by this note.

## 2026-10-27 operator: running V2 backend first-party classes absent

The operator inspected the **running** `prp-mcp-v2-backend-1`
JAR at `/opt/prp/app.jar` without changing the container or
printing JAR contents. Both exact Spring Boot archive entry markers
were reported `NOT_FOUND`:

- `BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkController.class`
- `BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkService.class`

Together with the running V2 frontend's three `NOT_FOUND` JavaScript
markers, this is strong evidence that **both live V2 artifacts predate
the first-party OIDC account-linking implementation**. The JAR check
searched ZIP bytes with `grep -aFq`, not an independently parsed ZIP
central-directory listing; do not overstate it as a complete archive
attestation. Both reports came from operator-reported read-only
commands, not from an authenticated ChatGPT session.

### Release/upgrade boundary for real ChatGPT task reads

1. Do not treat the V2 route's `200 text/html` as browser feature
   readiness. Do not register active OAuth clients or expose a callback
   solely to test that stale build.
2. Existing V2 backend, gateway, MySQL and public route remain
   unchanged. No `docker compose up`, `flyway repair`, image swap,
   Nginx reload, production migration, Keycloak Admin REST write or
   PR merge follows from these checks.
3. In disposable CI or a **separately authorized isolated stack**,
   rebuild both PR #113 frontend and backend from a pinned source
   commit; assign a fresh MySQL schema/volume with separate credentials,
   preserve the existing V2 and old Staging persistent schemas and
   migration histories, and apply the reviewed clean migration
   lineage. Avoid using a production database or any populated legacy
   MCP schema, even as a convenient shortcut.
4. Prove the actual deployed artifact contains the first-party Vue
   callback and both backend OIDC classes; keep the feature OFF until
   reviewed Keycloak client, canonical public routes, owner consent,
   and HTTPS SNI/Host/Origin are verified. Disposable CI already
   tests some of these components but does not verify the active
   V2 running artifact.
5. Obtain independent G0 and authentic B2 backup/restore/install
   permissions *before* any active Realm, host, production or
   existing V2 cutover. Document precise new-stack resources, ports,
   state isolation, rollback owner, expected code SHA and target
   image digests in the separate change decision.
6. After authorization, complete real Keycloak browser PKCE identity
   linking, genuine ChatGPT OAuth, owner-scoped
   `prp_tasks_list` at most 20, revoked-token denial and finance/
   wellness/write denial. A fresh disposable test account is not
   the existing PRP production user's data. Production data
   integration, if requested later, needs **separate** permission
   and identity mapping; never silently point the staging OAuth
   connector at the production database.

This is an **implementation and change-review plan only**. It
creates no released artifacts, backup receipts, staging databases or
new public routes; it does not declare any next G0/B2 gate passed.

## Fresh-MySQL candidate: host preflight is NOT release authority (2026-10-27)

PR #113 now includes a **source-only** NewDB Compose review candidate,
`app/deploy/mcp-staging/compose.newdb.review.yaml`:
`prp-mcp-newdb-review`, distinct MySQL database
`matrix_prp_mcp_newdb_review`, project-namespaced volumes/networks,
strict loopback gateway `127.0.0.1:18083`, opt-in
`newdb-review` Compose profile, and all MCP/OAuth/first-party/write flags
hard-coded `false`. This is not installed on the operator host.

**CI evidence:** [40510048879](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40510048879)
used an ephemeral GitHub project with fresh MySQL, Java 21 PRP and Vue/Nginx.
It proved health, Host and API-path constraints, the canonical
**V24 vocal → V25 drafts → V26 grants → V27 links → V28 OIDC**
Flyway scripts, and the new OIDC table on an *empty* database.
CI explicitly destroyed only its own temporary project and volumes.
This does NOT establish backward compatibility of the existing V2
database or permission to change any persistent host.

`app/deploy/mcp-staging/host_newdb_readonly_inventory.py` is a
separate **host-side read-only review**. It queries Linux
`/proc/net/tcp` and `/proc/net/tcp6`, coarse available RAM/disk
and only Docker **name/published-port summaries** (`ps -a --format Names`, `ps --format Ports`, `volume ls`, `network ls`).
It flags any port-18083 host listener **or existing Docker TCP publish** (including Docker installations with no userspace proxy), conflicting
`prp-mcp-newdb-review` project artifacts, missing known V2/legacy
gateway container names, low review resources or unobservable Docker/TCP
facts. No secrets, inspected container environment, DB table records,
Host credentials, private paths, IP inventories or original container
metadata are printed.

A no-collision result is explicitly
`NO_COLLISION_OBSERVED_REVIEW_ONLY`, **not**
`approved-install.safe.json`, `fresh-b2-restore.safe.json`, a
rollout/rollback verification or G0 sign-off. Point-in-time port
availability cannot reserve that port. Resource thresholds are
preliminary, not a load/capacity test. Before any real host
deployment, an authorized operator still must independently review
Docker engine membership, limits, storage capacity, exact
source commit/image digests, test-only service access and the
existing V2/MySQL preservation plan; follow the original G0/B2
controllers and do not install from this note.

## Explicit blockers before authorization

- [ ] Independent G0 reviewer and accountable host operator identified;
      approval specifies exact files, target Realm, two client IDs, change
      window, rollback owner, maximum interruption and abort triggers.
- [ ] Verify the active 13-client Realm identity, *current* policies,
      profiles, client-scope mappers/defaults and CIMD interception.
      Earlier empty-policy observations are historical, not current proof.
- [ ] Independently back up and *restore-test* the current Keycloak
      PostgreSQL and relevant signing state; preserve exact backup ID.
      Previously missing `approved-install.safe.json` and
      `fresh-b2-restore.safe.json` cannot be fabricated or copied.
- [ ] Reconcile the original six-file Nginx guard/cutover controller
      and `18082` baseline with the separate new raw-URI/first-party
      browser-path candidates. No implicit wildcard `/api/**` exposure.
- [ ] Approve the actual PRP first-party SPA callback/login/grant API,
      secure CSRF/Host/SNI/TLS/referrer behavior and build/version lineage.
      The code in Draft PR #113 is not the running PRP V2 code.
- [ ] For Keycloak 26.8.x, independently decide on exact static
      preregistration versus native CIMD: disposable CI observed
      rejection of official `token_endpoint_auth_methods_supported`.
      **Do not silently disable an active CIMD policy.**
- [ ] Confirm ChatGPT's current advertised OAuth metadata and issuer
      compatibility before applying an approved target-only change.

## Required acceptance and rollback (after separate approval only)

1. Capture 13-client baseline and independently verified recovery point;
   demonstrate the ability to restore without changing production PRP.
2. Apply only the approved exact client additions; read back both clients
   and verify old 13 still intact, PKCE S256 enforced and no broad Scope,
   redirects, password/implicit/service-account flow or generic DCR.
3. Test real TLS public routes (including canonical-path enforcement),
   genuine `private_key_jwt` verification and auth code/token flow;
   verify actual `aud`, `iss`, `sub`, `azp`, consent, task scope,
   refresh/resource behavior and revocation.
4. In a real PRP V2 first-party browser login, verify the separately
   authenticated owner can bind exactly one signed `(iss,sub)`;
   verify real ChatGPT identity has compatible subject. Never expose
   password, callback code, PKCE verifier, Access Token or ticket in chat.
5. After actual ChatGPT account linking, call `prp_tasks_list` and
   confirm at most 20 records belonging to that PRP owner. Finance
   reads and all writes must fail without consent (writes remain OFF).
6. On any mismatch or broadened permission, **stop**. Independently
   restore the observed active V2/Realm baseline using the authorized
   rollback path. Preserve reports and do not auto-repeat a failed change.

## Decision / evidence discipline

**Current disposition: G0 NO-GO; B2 NO-GO;
LIVE_CHATGPT_OAUTH NOT VERIFIED; LIVE_TASKS NOT VERIFIED.**
A reviewer may sign an actual bounded authorization only after
checking independent evidence. This document, a SQL result and a
disposable CI green run are not signatures, deployment receipts or
authorization. No fake approval object or bypass should be generated.
