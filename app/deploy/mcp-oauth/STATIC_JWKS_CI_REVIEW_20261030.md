# Static JWKS client JWT CI review — NO-GO

Scope: disposable GitHub Actions Keycloak only. This document is **not** permission to run against live staging or production.

## Evidence
Keycloak 26.8.0 `ClientPublicKeyLoader.loadKeys()` checks `isUseJwksUrl()`, then `isUseJwksString()`, then the client certificate/public-key branch. Confirmed attribute names: `use.jwks.url`, `use.jwks.string`, `jwks.string`. This proves the code path exists, **not** that a ChatGPT assertion has been authenticated.

## Required repairs before CI execution
1. Bind the test to a container created in the same CI job. Validate container identity, immutable image digest and disposable Realm provenance; never rely solely on `GITHUB_ACTIONS=true`, `localhost`, or a container name.
2. Reuse the existing ephemeral CI administrator login instead of accepting an arbitrary admin token. Require disposable realm initialization and assert no pre-existing client.
3. Enforce negative responses as `400` with OAuth `invalid_client` where applicable. Do not treat any non-200 response as proof of signature rejection.
4. Ensure test cleanup runs even if client creation succeeds but the Location header is malformed. Never print tokens or JWTs.
5. Pin CI dependencies and prove the Python `cryptography` package is available.
6. Test wrong signature, unknown kid, wrong audience, expired assertion and positive client_credentials response. Include incorrect iss/sub and replay as separate probes when feasible.
7. Keep official ChatGPT JWKS out of synthetic signature tests. A synthetic RSA key proves only Keycloak's static-key path, not genuine ChatGPT token exchange.
8. Review static key rotation risk: the configured JWKS becomes stale when ChatGPT rotates signing keys.

## Deployment gates
Owner's narrowly scoped test-client authorization is **not** B2 approval. Do not modify existing clients, Realm-wide policies, Keycloak network, Nginx or production DB. Do not register a live ChatGPT client or attempt real OAuth until independent B2 acceptance and explicit change approval are documented.

Current verdict: **NO-GO**. The standalone test script is a draft, not integrated into the CI workflow and has no execution evidence.
