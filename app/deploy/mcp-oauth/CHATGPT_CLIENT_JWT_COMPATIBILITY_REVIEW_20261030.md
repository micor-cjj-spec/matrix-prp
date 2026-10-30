# ChatGPT private-key JWT / Keycloak 26.8 compatibility review

**Review-only; B2 NO-GO.** Based on `app/deploy/mcp-oauth/ci_chatgpt_cimd_pkce.py` on branch `test/mcp-authcode-privatejwt-refresh-20261024`. This is a static code review, not a live ChatGPT JWT verification.

## What disposable CI actually tests

- It registers the exact client ID `https://chatgpt.com/oauth/client.json` with `clientAuthenticatorType=client-jwt`, `publicClient=false`, JWKS URL `https://chatgpt.com/oauth/jwks.json`, callback `https://chatgpt.com/connector_platform_oauth_redirect`, and `pkce.code.challenge.method=S256`.
- It verifies a login-entry response for an authorization request including `openid offline_access prp.tasks.read`, PKCE rejection for missing/plain methods, client persistence, and a `prompt=none` error callback with `iss`.
- It does **not** authenticate a real ChatGPT private-key JWT at the token endpoint, complete user login/consent, exchange a code, or invoke `prp_tasks_list`.

## Specific remaining compatibility questions

1. **Assertion signing and JWKS:** Confirm the currently published ChatGPT JWKS is reachable by the actual Keycloak runtime and contains keys/algorithms accepted by the installed `client-jwt` authenticator. Do not assume the CI test's signing keys represent ChatGPT.
2. **JWT claims:** Verify Keycloak's expected `iss`, `sub`, `aud`, `exp`, `iat`, `jti` requirements against a real ChatGPT assertion. The token endpoint audience must match the actual public token URL; never infer success from a login page.
3. **Token endpoint authentication method:** Confirm AS metadata and the actual Keycloak client representation agree on `private_key_jwt` / `client-jwt`; these are different nomenclatures at the OAuth metadata and Keycloak configuration layers.
4. **Issuer and resource:** Compare external `https://auth-test.micor.top/realms/prp-mcp` with discovery, authorization-response `iss`, and token `iss`. Check MCP resource audience `https://prp-test.micor.top/api/mcp` and explicit audience mapper output.
5. **Scope / refresh:** Validate `prp.tasks.read` and `offline_access` grants in a real approved flow, including refresh token rotation/revocation; static optional scope assignment does not guarantee usable tokens.
6. **Dynamic CIMD interaction:** CI disables a **disposable** policy named `ci-chatgpt-cimd-only` after preregistration. Never copy that policy modification to the live Realm; review actual live policies first.
7. **Negative cases:** Wrong `aud`, invalid `kid`, bad signature, expired assertion, replayed `jti`, missing PKCE and mismatched redirect should fail closed.

## Release gate

Before any Keycloak Admin API write: independent B2 approval, verified restore receipt, approved change scope and window, read-only Realm policy/client inventory, and explicit rollback authorization. The isolated restore and OIDC discovery pass do **not** satisfy this approval requirement.

**Status: REAL_CHATGPT_CLIENT_ASSERTION_UNVERIFIED; DEPLOYMENT_PERMITTED=NO.**
