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

## CI evidence update (2026-10-30)

Workflow run 40984224893 completed successfully for both disposable Keycloak 26.8.0 and 26.8.1. Raw job logs 123831317459 and 123831317045 each contain `EMBEDDED_JWKS_ROTATION_CI_PROOF=PASS`, covering overlapping keys, unknown kid denial, removal and rollback. This closes the synthetic rotation test item above, not the live-client or independent approval gates.

Operator read-only checks also observed empty `client-policies.policies` and `client-policies.profiles` arrays; public OIDC discovery on `auth-test.micor.top` returned HTTP 200 advertising authorization code, PKCE S256 and private_key_jwt. The same-domain discovery path returned HTTP 503. No live configuration was changed.

## Exact-client parity gap and operational guardrails

The existing `review_chatgpt_single_client.py` checks equality to a URL-JWKS proposal (`use.jwks.url=true` and `jwks.url=https://chatgpt.com/oauth/jwks.json`). It **rejects** any inline-JWKS variant as a changed shape. Therefore the successful disposable rotation CI is not approval to deploy an inline-JWKS version of that candidate.

Before a future approved registration, prepare a separate review-only, exact-one-client candidate whose immutable fields are the official metadata client ID, redirect URI, `client-jwt`, authorization code, PKCE S256, resource audience and least-privilege scopes. Its only reviewed key-source change may be client-local `use.jwks.url=false`, `use.jwks.string=true`, and a validated public-only `jwks.string` snapshot. Never embed private fields or hard-code the current `kid` as permanent. Do not derive permission to create a first-party client or alter existing clients.

The source of truth for key changes remains the official metadata's `jwks_uri`; use full-set comparison (kid plus RSA n/e), detect duplicate kid or changed material under the same kid, and record a sanitized fingerprint. An external fetch is a snapshot, not proof of a provider overlap window. Alert-only monitoring and human-approved updates are the default. A removal is not safe merely because the public endpoint no longer advertises a key; account for outstanding assertions and approved rollback timing.

A new disposable CI should exercise the **exact single-client candidate shape** under authorization-code/PKCE with synthetic client assertions, not only client-credentials. It cannot prove real ChatGPT signing or external-browser connectivity. Maintain B2 NO-GO until independent recovery evidence and approval exist.

## Operator offline validator execution (2026-10-30)

Operator ran `python3 -m unittest -v test_review_chatgpt_inline_jwks` using three files extracted from the review branch into a temporary directory. `test_reject_invalid` and `test_valid_review_only` both passed: `Ran 2 tests ... OK`; the operator output ended `OFFLINE_JWKS_UNIT_TEST_COMPLETE=YES` and `NO_KEYCLOAK_CHANGES=YES`. These are offline unit tests, **not** an authorization-code/PKCE plus embedded-JWKS integration test or approval to register a client.
