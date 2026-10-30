# ChatGPT offline JWKS rotation — review only (2026-10-30)

**Status: NO-GO. This is not a deployable payload, approval, or instruction to modify live Keycloak.**

## Verified operator observations

- Live test Realm `prp-mcp` exists with 13 existing clients; exact ChatGPT client ID is absent. `prp-first-party-link` is also absent but is **out of creation scope**.
- Required Realm scopes `basic`, `prp.tasks.read`, `offline_access` exist (not proof of assignment).
- Host fetch of `https://chatgpt.com/oauth/client.json` returned HTTP 200 and advertised `jwks_uri=https://chatgpt.com/oauth/jwks.json`, `token_endpoint_auth_method=private_key_jwt`, and callback `https://chatgpt.com/connector_platform_oauth_redirect`.
- Host fetch of the declared JWKS returned HTTP 200, one RSA / RS256 key with observed `kid=cimd-20260428030119`. **This is a point-in-time observation, not a permanent pin.**
- Live Keycloak's only observed Docker network `prp-mcp-oauth-stage_auth_private` has `internal=true`. Container HTTPS reachability was **not** tested: curl/wget/jshell absent and a later shell pipeline exited early. Host egress is not container egress.
- CI #346 (run 40981992725) passed on disposable Keycloak 26.8.0 and 26.8.1 with synthetic inline JWKS. No real ChatGPT assertion was tested.

## Review-only rotation model

1. **Source of truth:** retrieve the exact `jwks_uri` from the official HTTPS client metadata. Fetch JWKS over verified TLS from an independently authorized trusted network location. Never infer the JWKS URL from a guessed `.well-known` path.
2. **Input validation:** require a JSON object with a nonempty `keys` array; reject duplicate `kid`, duplicate key material, malformed base64url RSA modulus/exponent, private fields (`d`, `p`, `q`, `dp`, `dq`, `qi`, `oth`), non-RSA or non-RS256 signing keys, and unexpected source/redirect/client ID. Avoid logging complete keys or tokens.
3. **Staged review:** compare the full prior approved public-key set against the newly fetched set by `kid` and public parameters. Flag additions, removals, or changed material under an existing `kid`; no automatic live writes.
4. **Rollover:** when the provider overlaps old and new signing keys, a reviewed client-local inline JWKS may temporarily contain both public keys. Never assume overlap will be available; if the provider rotates without overlap, owner must accept a possible authorization outage pending review. Never accept unknown `kid` by disabling signature validation.
5. **Fail closed:** if metadata/JWKS fetch, TLS verification, structure checks, independent approval, or rollback readiness fails, do not update live Keycloak. Preserve the last approved client-local public keys only within their separately approved validity policy; do not assert old keys remain valid indefinitely.
6. **Change boundary:** after B2 independent sign-off, any future write must target **only** the newly approved exact ChatGPT client and its own attributes. Do not modify existing clients, global policies/profiles, Nginx, Docker networks, or production data.
7. **Evidence and rollback:** record timestamp, official source URI, approved key IDs, sanitized fingerprints, reviewer identity/approval, previous approved client-local configuration, and a tested rollback procedure. Never record secrets or private key material.

## Missing proof before implementation

- Independent B2 approval and restore/rollback evidence.
- Live Realm policy/profile inventory and confirmation no realm-wide changes are needed.
- A controlled disposable test proving **two-key overlap, unknown-kid denial, old-key removal, and rollback** for the exact client shape.
- Real ChatGPT signed `private_key_jwt` end-to-end OAuth verification.
- An authorized, operational key-refresh mechanism and explicit owner decision about outage tolerance; a one-time embedded JWKS snapshot is insufficient.

**Decision: NO-GO; do not register or alter live clients.**
