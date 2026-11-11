# Keycloak JWT client-authentication failure: isolated event evidence

## Production incident boundary

The **real ChatGPT** authorization completes Keycloak login but the production
Keycloak 26.8.1 `/token` call returns HTTP 400 and records
`CODE_TO_TOKEN_ERROR / invalid_client_credentials`, without an event detail.
There is **no evidence of which client assertion check failed**. The original
production policy JAR was independently shown byte-for-byte equal to the
181-check successful CI artifact; that success uses a synthetic signer.

The upstream Keycloak fix [#54365](https://github.com/keycloak/keycloak/pull/54365)
and 26.8 backport [#54629](https://github.com/keycloak/keycloak/pull/54629),
merged November 10, 2026, add `authentication_error_detail` to relevant
failed-client authentication events. The change improves **observability**,
not JWT acceptance. Production 26.8.1 predates it.

## Test 1: PRP integrated baseline, Keycloak 26.8.1

`ci_auth.py` on a disposable GitHub-hosted runner:

1. Enables only `CODE_TO_TOKEN_ERROR` and `CLIENT_LOGIN_ERROR` events in
   its temporary Realm for 900 seconds.
2. Sends a synthetic invalid RSA signature bearing a public official JWKS
   `kid` to the runner's private Keycloak. It verifies JVM JWKS fetch and
   native refusal before synthetic signing credentials are injected.
3. Requires the `invalid_client_credentials` event to have been persisted.
4. Prints only booleans. Never prints JWT, secrets, or raw event details.

**Evidence:** PR #161, isolated CI run 42940272545, Job 130260143248.
`HEALTH_AUTH_CANDIDATE_SUCCESS checks=184`; the safe log reports
`event_observed=true`, `authentication_error_detail_present=false`.
This confirms the old-version *missing-detail behavior*, not the real
ChatGPT signing failure.

`PRP_REQUIRE_JWT_AUTH_DETAIL=1` optionally enforces a nonempty detail for
a separately reviewed, patched instance. It is **not** required on 26.8.1.

## Test 2: executable before/after comparison of the upstream patch

`jwt_event_compare_ci.py`, run only by
`.github/workflows/keycloak-jwt-event-comparison.yml` on a disposable GitHub
runner, compares **the same synthetic invalid algorithm assertion** against:

- The official Keycloak **26.8.1** container;
- The **same 26.8.1** container with only three Keycloak Services Java
  sources patched from fixed upstream commit
  `0b48783ead3b9ad8cb72428c1263c649ad43633a`.

The job checks out the base source and fixed upstream commit, applies the
upstream diff, compiles eight classes, overlays the temporary Services JAR,
and re-augments the **test-only** Keycloak image. Both instances import the
same synthetic Realm, use a local development database, and reject a test
JWT with `alg=none`. The job reads authentication events through an
isolated Admin API, reporting only booleans and an exact expected-message
match, not the actual event values.

**Evidence:** PR #161, GitHub Actions run 42945552066,
`keycloak-jwt-event-comparison` job **SUCCESS**:
- Baseline: `invalid_jwt_rejected=true`, `event_observed=true`,
  `error_detail_present=false`.
- Patched: `invalid_jwt_rejected=true`, `event_observed=true`,
  `error_detail_present=true`, `expected_algorithm_detail=true`.
- `PINNED_UPSTREAM_JWT_ERROR_DETAIL_COMPARISON_PASS`.

The first attempt failed due to a transient container-start socket reset.
The retry tolerance and public **synthetic** Realm import permissions were
corrected; the subsequent test passed.

## Non-goals / production gates

This reconstructed temporary CI image is **not a Keycloak official release**
and is **not approved for production deployment**. It runs a test-only
configuration, not the live Keycloak + PostgreSQL deployment. Neither case
contains OpenAI-managed signing keys, real ChatGPT JWTs, real users, nor any
production database or data. Passing this test does **not** mean the PRP
OAuth connection works.

Do **not** send live `client_assertion`, authorization codes, tokens or
Keycloak bootstrap secrets to logs, issues, scripts or third parties. Do
not weaken `private_key_jwt`, S256, exact resource or health scopes.

A production upgrade must be based on a **separately reviewed official
release containing the backport**, together with provenance/digest review,
production state backup and isolated restore, maintenance approval,
rollback, and a real ChatGPT authorization attempt. The real error's
specific failure detail must be checked in a *time-limited*, minimally
privileged diagnostic window and only a non-sensitive classification
retained. Production remains OAuth **NO-GO** until true end-to-end success.
