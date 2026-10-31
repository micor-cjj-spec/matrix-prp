# B2 isolated Keycloak application restore — operator output (2026-10-30)

**Technical result: PASS for application startup and OIDC discovery. Authorization: NO-GO.**

This is a transcription of operator-provided terminal output, not an independent audit receipt or authorization.

## Environment and isolation

- Temporary Docker internal network: `prp-mcp-b2-apprestore-net`, `Internal=true`.
- Temporary restored PostgreSQL: `prp-mcp-b2-apprestore-db`, `postgres:17.6-alpine`, isolated network, no production volume.
- Temporary Keycloak: `prp-mcp-b2-apprestore-kc`, same immutable image ID as staging Keycloak 26.8.0 (`sha256:e2508edb35d7b3b39468c3e4e77da4e3c8dca8968b055259d60ccfbd29d65e59`).
- Connection: `KC_DB_URL=jdbc:postgresql://prp-mcp-b2-apprestore-db:5432/restore_test`.
- Keycloak published host ports: none.
- Restored realm names: `master`, `prp-mcp`; `prp-mcp` client count: 13.
- Archive SHA256: `0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17`.

## Keycloak startup

First attempt with `--read-only` failed during Quarkus augmentation writing `/opt/keycloak/lib/quarkus/transformed-bytecode.jar`. The subsequent isolated Keycloak instance is running; log reports:

- `Quarkus augmentation completed`
- `Bootstrap completed in 15.378000 seconds`
- `Keycloak 26.8.0 ... started in 45.994s. Listening on: http://0.0.0.0:8080`

Keycloak image has no `curl` or `jshell`; neither absence indicates service failure.

## OIDC discovery check

Operator used host Python `urllib.request` against the **isolated container IP** `192.168.64.3:8080`, requesting `/realms/prp-mcp/.well-known/openid-configuration`. Results:

```text
OIDC_HTTP_STATUS=200
OIDC_ISSUER=http://localhost:8080/realms/prp-mcp
AUTH_ENDPOINT_PRESENT=true
TOKEN_ENDPOINT_PRESENT=true
OIDC_DISCOVERY=PASS
APPLICATION_RESTORE_VALIDATION=COMPLETE
B2_DEPLOYMENT_PERMITTED=NO
```

The localhost issuer is expected for this temporary configuration, **not** an externally usable ChatGPT OAuth issuer.

## Limits / follow-up

- Confirms Keycloak startup and OIDC metadata response from restored DB; does not verify login, authorization-code issuance, refresh, full application recovery objectives or data row equality.
- Evidence is operator-reported; no independent B2 reviewer approval, no `approved-install.safe.json` or `fresh-b2-restore.safe.json` acceptance receipt.
- No existing Keycloak Realm, Nginx, production DB or OAuth client was modified by these test steps.
- At time of this record the two temporary containers and network are still present. **Cleanup is pending**; verify exact names/network before removal.
- Deployment permission remains **FALSE** until independent review and explicit change authorization.
