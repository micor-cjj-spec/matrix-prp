# JWT client authentication error: isolated evidence test

## Why

The production PRP ChatGPT OAuth callback reaches the Keycloak 26.8.1
`/token` endpoint, which returns `CODE_TO_TOKEN_ERROR /
invalid_client_credentials`. The event has no detail fields. Production
`private_key_jwt`, RS256, official JWKS URL, resource and PKCE requirements
remain unchanged.

Upstream Keycloak [#54365](https://github.com/keycloak/keycloak/pull/54365)
and the 26.8 backport [#54629](https://github.com/keycloak/keycloak/pull/54629)
(the latter merged November 10, 2026) propagate an authentication failure
description to the event's `authentication_error_detail` field. They improve
**diagnosis**, not JWT acceptance. Keycloak 26.8.1 predates that fix.

## What this PR tests

The existing `ci_auth.py` runner is explicitly restricted to ephemeral
GitHub-hosted CI. Before any synthetic client credential substitution, it:

1. Enables only `CODE_TO_TOKEN_ERROR` and `CLIENT_LOGIN_ERROR` events
   in its **temporary** Keycloak realm, with 900-second retention.
2. Uses a synthetic private key to sign an intentionally invalid assertion
   claiming the **public** official JWKS `kid`. The JWT travels only to the
   isolated Keycloak instance, never the production endpoint.
3. Checks that Keycloak rejects the signature and actually fetched the
   official JWKS, as it did before this change.
4. Queries only the isolated realm's events and verifies
   `invalid_client_credentials` was persisted.
5. Prints solely `event_observed` and
   `authentication_error_detail_present` booleans. **Never print event
   details, JWT, tokens, private keys, credential values or identities.**

The original 26.8.1 baseline does **not** require a non-empty detail. To test
a reviewed Keycloak image containing the upstream change, use the same
disposable runner **after independently pinning and verifying the patched
image** and set `PRP_REQUIRE_JWT_AUTH_DETAIL=1`. That opt-in turns event
detail into a required CI gate; merely setting it against 26.8.1 is not a
valid patched-image test.

No patched-image build or runtime result is claimed by this PR. A production
rollout additionally requires independently reviewed image integrity, a
production-state backup and restoration rehearsal, maintenance approval and
a **real ChatGPT** connection retry. Synthetic signatures cannot prove
OpenAI-managed `private_key_jwt` acceptance.

## Safety

Do not run this CI harness on the production server. It creates disposable
PostgreSQL, Keycloak, Nginx and synthetic credentials and expressly forbids
production data. No production Realm, Docker Compose, Nginx, database or
client-auth configuration is changed by this PR.
