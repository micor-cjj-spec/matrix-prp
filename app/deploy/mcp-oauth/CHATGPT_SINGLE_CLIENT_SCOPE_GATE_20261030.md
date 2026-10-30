# ChatGPT single-client scope gate — 2026-10-30

## Owner-authorized boundary

The owner's authorization covers **only creation** of the exact Keycloak test-Realm client ID `https://chatgpt.com/oauth/client.json` and essential attributes **on that new client**. It does not authorize:
- creating or modifying `prp-first-party-link` (although it may be inventoried read-only);
- changing any pre-existing client, Realm policy/profile, global client scope, mapper on another client, Nginx, production database, or server service;
- overriding B2 independent approval, restore verification, or rollback gates.

The legacy `review_exact_client_registrations.py` generates **two** candidate clients and is therefore **not an approved deployment payload** for this narrowly authorized operation. Never feed its JSON into an installer or Admin API.

## Existing safe live inventory (operator-executed only)

Use the already-reviewed script `app/deploy/mcp-oauth/keycloak-resource-guard/live_exact_client_readonly.sh`, which requires a full 40-hex immutable Git pin, checks the expected existing PostgreSQL container, and runs `realm_scope_readonly.sql` within `BEGIN TRANSACTION READ ONLY`. It emits only Realm/client counts and required scope presence. It does **not** inspect policies or establish approval.

Expected invariant from older evidence: Realm name `prp-mcp`, historical client count 13, exact ChatGPT client absent. These values are **not** fresh live observations; a changed count or existing exact client is a stop-and-review condition.

Do not assume a read-only SQL snapshot proves official JWKS reachability from the live Keycloak network. Do not run or modify Nginx, Docker services, or Keycloak policies to repair egress.

## Release gates

1. Independent B2 reviewer approval and fresh restore/rollback evidence: **MISSING / NO-GO**.
2. Current live exact-ID absence and client/scope inventory: **NOT RECHECKED THIS TURN**.
3. Current live policy/profile inventory: **NOT RECHECKED THIS TURN**.
4. Official JWKS reachability from live Keycloak: **NOT RECHECKED THIS TURN**.
5. Real ChatGPT signed `private_key_jwt` and full end-to-end OAuth: **UNVERIFIED**.
6. Disposable Keycloak 26.8.0 and 26.8.1 embedded-JWKS test: **PASS**, run 40981523689, synthetic keys only.

**Decision: NO-GO.** No live client registration, no policy changes, no production changes.
