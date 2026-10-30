# Embedded JWKS Keycloak CI evidence — 2026-10-30

## Proven in disposable GitHub Actions only

- Repository: micor-cjj-spec/matrix-prp
- Review PR: #130 (Draft); branch: `review/mcp-chatgpt-prereg-no-go-20261030`
- Workflow: `MCP OAuth disposable Keycloak smoke`
- Run: https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40981523689
- Jobs: Keycloak 26.8.0 ID `123822471208`; Keycloak 26.8.1 ID `123822471632`.
- Both jobs: completed / success. Maven, disposable Keycloak integration, SPI hash and artifact retention steps succeeded.
- Both raw job logs explicitly contain:
  - `PASS EMBEDDED_JWKS_valid`
  - `PASS EMBEDDED_JWKS_wrong_signature`
  - `PASS EMBEDDED_JWKS_wrong_kid`
  - `PASS EMBEDDED_JWKS_wrong_audience`
  - `PASS EMBEDDED_JWKS_expired`
  - `EMBEDDED_JWKS_CI_PROOF=PASS`
- The test creates a random disposable client, uses `client-jwt`, `use.jwks.string=true`, `use.jwks.url=false`, a synthetic RSA-2048 RS256 key and `client_credentials`. The temporary client is deleted in `finally`.
- The official JWKS reachability probe succeeded **from the disposable runner**, and rejected an untrusted assertion.

## Not proven / must not be inferred

1. No real ChatGPT private key or signed assertion was used. `REAL_CHATGPT_JWKS_ASSERTION=UNVERIFIED`.
2. The live test Realm's outbound reachability, exact client registration and token exchange remain unverified. The runner's egress result does **not** establish server egress.
3. The embedded JWKS client-credentials test is **not** the complete ChatGPT browser authorization-code + PKCE + refresh flow with actual ChatGPT signing keys.
4. CI's disposable-container checks (loopback base, image, container name, label) are not cryptographic attestation of runner provenance.
5. No production DB, Nginx, global Realm policies, existing clients, or live Realm was changed by this review CI.
6. The owner's limited authorization to add one exact client to the test Realm does not waive the independent B2 NO-GO gate.

## Decision

**B2 = NO-GO; PR #130 remains Draft.** Do not register the real client or re-attempt ChatGPT connection yet.

## Next evidence needed (read-only, before any live change)

- Identify and verify the exact live test Realm and the pre-existing clients; confirm exact ChatGPT client ID is absent.
- Read current Realm client policies and verify no global policy change is needed.
- Confirm approved rollback/backup and independent B2 sign-off; stop on any mismatch.
- Establish whether live Keycloak can obtain the official JWKS or requires a reviewed client-local inline JWKS configuration; do not assume GitHub runner network equals live network.
- Only after the gates pass, propose a minimal diff restricted to creating `https://chatgpt.com/oauth/client.json` and its own attributes, with explicit no-modification checks.


## Owner-scoped single-client regression — CI #346

- Commit under test: `4d0f74726081b1901574dfc997751cf8b16dffda`.
- Workflow run: https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40981992725
- Keycloak 26.8.0 job `123823998990`: **completed / success**.
- Keycloak 26.8.1 job `123823999252`: **completed / success**.
- Both jobs passed the added `test_review_chatgpt_single_client.py` contract in step 4.
- Both jobs passed disposable Keycloak integration step 8, SPI artifact hash and retention steps 9–10.
- Raw logs from both jobs contain all five `PASS EMBEDDED_JWKS_*` checks and `EMBEDDED_JWKS_CI_PROOF=PASS`.
- An earlier regression run `40981929586` failed only because the new unit test incorrectly expected the intentional `None` default to raise; commit `4d0f747` corrected the test, and CI #346 passed.
- The review branch has additional evidence documentation commits after the tested commit; this entry records the **exact tested SHA** rather than claiming later commits were exercised.
- No live test Realm change is implied; B2 remains **NO-GO**.
