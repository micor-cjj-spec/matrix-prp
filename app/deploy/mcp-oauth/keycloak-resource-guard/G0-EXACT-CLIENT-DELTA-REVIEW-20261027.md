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
