# Keycloak 26.8.1 Client Policy resource refresh proof-of-concept

**CI-ONLY. This is not reviewed production code. Do not install this JAR on the
shared staging/production Realm.** No deployment scripts reference it.

## Precisely observed failure

With stock Keycloak 26.8.0 and 26.8.1, the synthetic Authorization Code +
PKCE S256 + signed `private_key_jwt` flow issues an RSA-verified MCP-audience
access token. A subsequent `refresh_token` request with a different `resource`
returns HTTP 200 even though only the canonical PRP audience is granted.
The newly issued JWT still has the canonical MCP audience, with no foreign
resource audience. This does **not** demonstrate cross-resource token leakage,
but violates the stricter PRP local authorization-server deny policy.

## Isolated SPI proof

The Java 21 Maven artifact implements Keycloak's actual
`ClientPolicyExecutorProviderFactory` SPI, and uses the real
`TokenRefreshContext.getParams()` API. The GitHub Actions job builds the
JAR, mounts it into an isolated, disposable Keycloak 26.8.1 container,
then registers a synthetic profile and client policy via Admin REST.
The policy is CI-only and the implementation changes behavior **only** when
`TokenRefreshContext` belongs to `ci-authcode-private-jwt`.

* A single explicit `resource` exactly equal to
  `https://prp.staging.example.org/api/mcp` is allowed.
* Zero explicit `resource` values leave the original resource on refresh;
  the test verifies the new access JWT stays canonically audience-bound.
* Any other explicit resource or a multi-resource request throws
  `invalid_target` before refresh is issued.
* Existing invalid signed assertions, unauthorized finance scope, replay
  after rotation and revocation remain rejected.
* The provider does not accept or log real ChatGPT keys, production tokens,
  or PRP user credentials.

The test must verify read-back of the policy, actual invalid-resource denial,
real positive token refresh, RSA signature, audience, rotation, replay, and
revocation. A successful JAR build alone is not sufficient.

## Not yet sufficient for active Keycloak

Before any production-grade implementation: remove CI-hardcoded identifiers;
make client and allowed resources an audited typed configuration; require an
explicit policy selection for the exact ChatGPT client; provide unit/negative
tests for duplicate `resource` parameters, policy precedence, missing/invalid
client configuration, and other clients' regression. Verify the compiled
provider on an isolated restoration of the actual active Realm and existing
clients, including signing and rollback, and independently satisfy B2,
Nginx/Host/SNI, staging acceptance, user binding, authorization and
ChatGPT-created OAuth token requests. Do not assume real ChatGPT sends
`resource` on each refresh until observed in controlled tests.

Official API basis: Keycloak 26.8.1 client policy executor SPI,
`org.keycloak.services.clientpolicy.context.TokenRefreshContext`,
and RFC 8707 §2.2 (per-server resource policy).
