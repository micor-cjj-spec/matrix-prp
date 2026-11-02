# PRP V2 ChatGPT OAuth: scoped staging change handoff (2026-11-02)

**Initiation:** On 2026-11-02 the PRP owner explicitly requested: “开始变更吧”.
This **starts preparation of a staging-only change request**. It does **not**
claim an independent G0/B2 approval, an accepted recovery receipt, or
authorization for a shared live Keycloak/Nginx transaction. Follow existing
release-controller policies; never rewrite their hashes or invent receipts.

**Tracking:** [Issue #149](https://github.com/micor-cjj-spec/matrix-prp/issues/149) ·
[Draft PR #131](https://github.com/micor-cjj-spec/matrix-prp/pull/131).

## Exact target and allowed delta

| Property | Fixed target |
|---|---|
| Existing ChatGPT app | PRP (dev mode); keep existing app ID/configuration |
| Public MCP resource | `https://prp-test.micor.top/api/mcp` |
| OAuth issuer | `https://auth-test.micor.top/realms/prp-mcp` |
| Current intended V2 public upstream | `127.0.0.1:18082` |
| Realm | `prp-mcp`; preserve 13 pre-existing clients |
| New client candidates | exact `https://chatgpt.com/oauth/client.json` and `prp-first-party-link` |
| Scope / MCP tools | `prp.tasks.read` only / `prp_tasks_list`, `prp_task_get` |
| Runtime | existing isolated V2 frontend + backend only; OIDC controller/service, callback/start/finish, V29 on V2 clone first |
| Source under review | PR #131 commit `1c1b1c41aad5dea8e8292dcc2ff715822c0d04c2`; no unreviewed tag or `latest` |
| Writes / Flyway in production | both disabled; no production DB migration |

Never change `matrix-prp.service`, `matrix_prp` production MySQL,
the legacy `18081` service, the separate proposed `18083` NewDB stack,
the existing 13 clients or the protected `main` publication hold.
No general `/api/**` proxy, wildcard client registration, permissive
OAuth scopes, implicit dynamic client registration or downgrade of TLS.

## Existing technical evidence (do not redo without drift)

- PR #131 source-only checks: 15/15 at `1c1b1c41aad5dea8e8292dcc2ff715822c0d04c2`, including browser,
  Keycloak, V24→V29 disposable database upgrade/restore and authorization
  tests. These tests are synthetic and do not prove genuine OpenAI-signed
  `private_key_jwt` or real owner task access.
- External fixed-URL OAuth public GET-only checks passed:
  https://github.com/micor-cjj-spec/matrix-prp/actions/runs/41377833789
  The public PRM advertises exactly `prp.tasks.read`.
- The **Oct 28 current test Realm backup was actually restored** into
  a private 101-table clone, with 13 original clients preserved, public
  signing JWKS parity and exact-two-client create+rollback *in clone only*.
  Evidence: `app/deploy/mcp-oauth/keycloak-resource-guard/CURRENT-KEYCLOAK-RESTORE-TECHNICAL-ACCEPTANCE-20261028.md`.
  Not an independently accepted B2 receipt; a cutover freshness check
  may demand a new <=3600-second time-of-change recovery witness.
- Actual running V2 inspected earlier lacked V29/first-party backend and
  Vue callback artifacts; active Realm lacked the two exact clients.
  That observed runtime has **not** been changed by this handoff.

## Mandatory hold points for the authorized operator

**G0 — independent decision before any shared host/config mutation:**
1. Identify accountable independent approver, maintenance window,
   no-go/abort triggers, rollback operator and exact environment scope.
2. Capture **current** six-file Nginx lineage, V2 Compose local modifications,
   V2 database and the current 13-client Realm/policies/mappers. Compare
   to the reviewed pins; a drift or unexpected component is a stop.
3. Old B2 guard/test vhost expects `18081` and **must NOT** be installed
   or re-pinned onto V2. The newer raw-URI reviewed candidate targeting
   `18082` and the additional first-party browser-route allowlist need
   a **separately versioned, independently approved V2 transaction**.
4. Ensure the original G0/B2 change controller accepts a genuinely scoped
   approval and a separately verified, adequately fresh Keycloak recovery.
   Last observed `approved_install=MISSING`,
   `fresh_b2_restore=MISSING`. Neither assistant nor script may
   synthesize or backdate these. No approval = stop.

**G1 — reviewed build and private rehearsal:**
5. Produce/verify immutable deployable backend/web image digests against
   the approved exact source. CI-only Docker image IDs are not published
   deployable artifacts. No `latest` or unpinned image substitution.
6. In **a separate private restored V2 clone**, verify V28→V29,
   first-party routes, migration rollback, least-privilege identity and
   existing V2 data safety; never run an unapproved migration on the live
   V2 or production `matrix_prp` volume.

**G2 — approved staged installation (not authorized by this document):**
7. Preserve operator-owned V2 Compose overrides; install only the reviewed
   V2 components, exact `18082` Nginx routes and selected
   Keycloak client/policy deltas. Require original controller approval,
   signed/provenanced receipts and before/after inventories.
8. Check the old 13 Keycloak client representations/policies did not drift,
   original PRP and legacy staging stayed healthy, raw-URI aliases
   were denied, canonical discovery and 401 challenge remain correct.
   Any failure: stop, execute the separately verified **authorized**
   rollback to the actual 18082 baseline (not legacy 18081), and
   independently verify recovery.

**G3 — real ChatGPT acceptance:**
9. Only after actual G0/G1/G2 approval+success, owner connects the
   **existing** PRP dev app. Verify real authorization code/PKCE S256,
   OpenAI-signed client assertion, issuer+resource audience, first-party
   PRP test-account link, exact task-only tool list, <=20 owned tasks,
   foreign-owner denial, and token/grant revocation. Keep all write
   endpoints/tools OFF. Do not paste tokens, cookies, private keys,
   real user rows or PostgreSQL dump contents into GitHub or ChatGPT.

## Current disposition

**PREPARATION STARTED / RELEASE NO-GO.** This file is a change-scope
handoff, not an installation script, formal approval or release receipt.
The production PRP MySQL backup/export program remains paused at owner's
prior direction; the separate eventual in-process producer task-read
release is tracked in Issue #127 and is **out of scope** here.
