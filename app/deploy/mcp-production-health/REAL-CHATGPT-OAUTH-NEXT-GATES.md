# PRP production ChatGPT OAuth — next gated actions (2026-11-11)

**Status:** production OAuth NO-GO. All actions in this file are review-only unless the
operator obtains separate approval for an exact production change. This file is
not a deployment instruction, and the experimental upstream-overlaid Keycloak
CI container must NEVER be deployed to production.

## 1. Actual observed failure and what is already excluded

- Production realm: `prp-mcp-prod`. Client ID:
  `https://chatgpt.com/oauth/client.json`, configured with `client-jwt`,
  `use.jwks.url=true`, JWKS URL `https://chatgpt.com/oauth/jwks.json`,
  RS256 and PKCE S256; configuration was checked through the production
  Keycloak Admin API. Public metadata is not proof of credential acceptance.
- Real user ChatGPT authorization reached the Keycloak token endpoint;
  Keycloak returned HTTP 400. A **real** short-lived event capture confirmed
  `CODE_TO_TOKEN_ERROR / invalid_client_credentials`. The stored event has
  **zero detail fields** on production Keycloak 26.8.1.
- A network-namespace curl test proved an outbound path via the dedicated
  egress proxy to OpenAI's published JWKS. It did **not** prove JVM client
  authenticator JWKS usage or the signature of the actual ChatGPT assertion.
  Docker logs at `KC_LOG_LEVEL=error` provided no useful reason.
- CI isolated Keycloak 26.8.1 and official 26.8.2 each passed **184**
  synthetic integration checks. Official upstream diagnostic backport
  `0b48783ead3b9ad8cb72428c1263c649ad43633a` was verified in an
  isolated runtime to persist `authentication_error_detail` for synthetic
  invalid JWT input. The backport is *observability only*, not a client-auth fix.
- **Keycloak 26.8.2** was published November 5; the backport was merged
  November 10. Do not assume 26.8.2 contains the diagnostic patch.

## 2. Verified backup evidence

- Encrypted production Keycloak PostgreSQL backup:
  `prp_health_auth_20261111T034648Z.dump.gpg` (86,459 bytes),
  SHA-256
  `ffd430b801b8daa145c82c88806edd037eddbe2f8b67b4040efd2baca9037dcc`.
- Operator completed decryption, 101-table PostgreSQL restore, Realm/client/
  key-provider/user count parity, isolated Keycloak startup, OIDC discovery,
  JWKS public set equality, and **actual clone JWT RS256 signing / validation**.
- Verified production JWKS public-set fingerprint:
  `521b2cf4581cfdff6178c0cd9cce541f73f29fb85e5322bdf598cf75b12eb733`.
- Backup has been **downloaded to the user's computer**. This establishes
  that a copy was reportedly made, but does NOT yet prove its local bytes
  match the original SHA-256 or that the decryption passphrase is separately
  recoverable. Do not claim off-host integrity until the local hash matches.

### Windows local integrity check (safe; no backup content printed)

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "$HOME\Downloads\prp_health_auth_20261111T034648Z.dump.gpg" |
    Select-Object -ExpandProperty Hash
```

If downloaded elsewhere, use the file's actual local path. Expected hash:
`FFD430B801B8DAA145C82C88806EDD037EDDBE2F8B67B4040EFD2BACA9037DCC`.
Keep backup ciphertext and passphrase in separate, protected locations. Never
upload private keys, dump, OAuth codes, JWTs, browser HAR or credentials.

## 3. Do not repeat already-completed checks

Do **not** rerun database restore, static client config, issuer/jwks metadata,
shared network namespace curl or event-detail SQL until a material dependency
has changed. Those questions have adequate evidence. Do not infer a cause
from `invalid_client_credentials` alone.

## 4. Next production diagnostic gate — after a *supported official release*

1. Verify that a **new official signed/tagged Keycloak release** contains
   merged backport `0b48783...`, rather than assuming a version number.
2. In CI and a disposable clone, test the official image + exact production
   Policy JAR digest; test upgrade of **the restored Realm** and JWT error
   event detail. Verify 26.8.2+ DCR migration behavior. Record image digest,
   policy JAR digest, SQL migration outcome and rollback test with original
   dump. Never test upgrades against the production database.
3. Require production operator's approval of exact deployment diff, health
   checks, downtime, restored-DB rollback procedure, and bounded change
   window before replacing a production Keycloak image. Do **not** roll back
   just the image if database schema/Realm changes have migrated.
4. On the approved version, temporarily enable ONLY required error-event
   storage and short retention through the authenticated Keycloak Admin API;
   record original event config and automate immediate restoration.
5. Perform exactly one genuine **PRP production plugin** ChatGPT Connect.
   Record time (UTC), HTTP status, event TYPE/ERROR, and a safe **fixed set
   of allowed diagnostic categories**. Do not print `client_assertion`,
   token, authorization code, entire event `details_json`, or raw HTTP body.
   Do not enable unrestricted DEBUG/TRACE.
6. Diagnose the real failure with the specific rejected client-auth
   condition, make the minimum corrective change in a reviewed candidate,
   and prove the real ChatGPT private_key_jwt code exchange and healthy
   MCP scope isolation in a controlled production window.
7. Restore original diagnostic settings and confirm Realm, login, signing,
   user data and health endpoints; roll back using the tested full restore
   procedure if new-version migration mandates it.

**Alternative while the release is pending:** escalate the sanitized
`/token` failure through official OpenAI support, providing the
non-sensitive timeline, Keycloak version, client authentication method, and
reproducible error classification. Do not submit token/JWT/header/cookie/HAR.

## 5. Acceptance criteria

The objective is not to make CI green (it already is): a **real** OpenAI-managed
`private_key_jwt` must be accepted, PKCE/resource must pass, PRP owner-only
health tools must be available, and forbidden scopes / unauthorized writes
must remain denied. No `none` / client secret fallback or broader scopes.
This is controlled by Issue #159, separate from any production approval.
