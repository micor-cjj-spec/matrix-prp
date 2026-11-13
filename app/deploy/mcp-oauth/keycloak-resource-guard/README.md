# Keycloak 26.8.1: PRP MCP refresh resource policy candidate

**Unreleased CI-only implementation. Do not install into an active test,
shared Realm, or production server.** The GitHub Actions workflow builds and
mounts the JAR only into a disposable Keycloak 26.8.1 Docker container; the
container and credentials are destroyed afterward. No deployment scripts
reference this module.

## Problem and boundaries

On stock Keycloak 26.8.0 and 26.8.1, a synthetic signed-client-JWT,
Authorization Code + PKCE S256 flow successfully refreshes even with
an unapproved alternate `resource` parameter. The newly signed access
token retains **only** the original canonical PRP MCP URI Audience, not
the foreign resource; this is **not** evidence of cross-resource access.
PRP nonetheless requires the stricter **deny noncanonical refresh input**
policy. This is a PRP-specific release gate, not a universal RFC 8707 MUST.

## Current Keycloak Client Policy Executor

The Java 21 Maven module implements Keycloak 26.8.1
`ClientPolicyExecutorProviderFactory`, `setupConfiguration`, and the real
`TokenRefreshContext.getParams()` token-refresh event.

The actual client-policy executor has two **typed, persisted** string inputs,
read back by the integration test:

| Configuration | Example in disposable CI | Constraint |
|---|---|---|
| `target-client-id` | `ci-authcode-private-jwt` | Exact, nonempty ID, no wildcards |
| `allowed-resource` | `https://prp.staging.example.org/api/mcp` | Exact HTTPS host and raw `/api/mcp` path; no other port, encoded alias, query, fragment, wildcard or userinfo |

This is the **synthetic fixture**, not the official ChatGPT ID or real PRP
URL. The Java module no longer hardcodes either identity.

In the disposable CI, the Client Policy is now additionally selected by
Keycloak's **built-in `client-attributes` condition**. The synthetic client
is marked with `prp.ci.refresh-resource-guard=enabled`, and this condition
is read back via authenticated Admin REST. A second unmarked client is
exercised independently; only the marked, exact configured target
client is affected, and only during `TOKEN_REFRESH`. It rejects missing,
duplicate, blank or noncanonical `resource` parameters with
`invalid_target`. It never prints or persists JWTs, cookies, assertions
or refresh tokens.

**Fail-closed behavior:** invalid executor configuration rejects all refresh
requests that *reach this executor*. A matching-client condition limits the
blast radius, but an administrator could misconfigure/remove the client
marker or executor, so stronger installed-policy provenance validation and
recovery remain necessary before touching a shared Realm. The disposable CI
also exercises restoring the previously existing policy and profile objects
after testing the additional profile/condition.

Keycloak currently rejects resource-omitted refresh with HTTP 400 even without
our executor's help. A real ChatGPT OAuth connection must therefore prove
that it sends the canonical `resource` on refresh, or use another separately
reviewed, compatible server policy. Never claim ChatGPT compatibility merely
because a synthetic CI client sends that parameter.

## Tests

The workflow runs seven Maven JUnit tests **before** loading the JAR into an
ephemeral Keycloak. The tests cover real SPI configuration binding,
canonical URI normalization pitfalls, exact client scoping, duplicate
resource values, missing parameters and malformed configuration.
Integration tests use actual Admin REST policy configuration/read-back,
real signed private-key JWT assertions, user PKCE authorization code,
canonical resource refresh, wrong resource/finance scope rejection,
refresh rotation, replay denial and token revocation.

## Remaining GO gates

1. Independent non-CI review of the candidate JAR with a target-only policy,
   configuration validation, rollback and all 13 restored Realm client checks.
2. Complete legitimate B2 approved install / fresh recovery evidence,
   unchanged Nginx Host/SNI/Authority gate and per-route public pairing
   approval. Do **not** synthesize missing receipts.
3. Real ChatGPT OAuth signed client and redirect testing, PKCE, refresh
   resource compatibility, token rotation/revocation, owner linking and
   authenticated read-only `prp_tasks_list`.
4. Only then consider a controlled separate V2 test deployment; never
   change production PRP, legacy Keycloak, original MySQL or write flag from
   this CI artifact.

API basis: Keycloak 26.8.1 client-policy executor SPI,
`org.keycloak.services.clientpolicy.context.TokenRefreshContext`,
RFC 8707 §2.2.
