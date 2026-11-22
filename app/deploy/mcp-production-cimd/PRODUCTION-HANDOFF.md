# PRP CIMD production handoff — review only (2026-11-11)

**Not approved for production. Do not run a cutover, merge the Draft PR, alter
Keycloak policies, issue credentials, restart auth services, or reconfigure Nginx
based only on this handoff.** This document keeps the existing production and
the previous `PRP` app intact.

## Intended ChatGPT plugin

- Candidate plugin: **PRP CIMD 验证版**, private version `0.1.0`,
  `https://chatgpt.com/plugins/plugins_6af4449c047c8191ba879fc2c5d8d891`.
- Current package `mcp.json` verified by Plugin Creator:
  `type=streamable-http`, `url=https://micor.top/api/mcp`,
  `auth.type=oauth`, `auth.client.mode=cimd`,
  `auth.resource=https://micor.top/api/mcp`,
  `auth.baseScopes=["prp.wellness.read"]`.
- No packaged static client ID/secret and no request for write scopes.
  Packaging or plugin creation **does not** prove it connected or that the host
  actually sent a signed `client_assertion`.
- Keep old `PRP` version `1.0.0` until new OAuth authorization and read-only
  MCP tools are proven end-to-end.

## Grounded candidate evidence

- Draft PR #162: source head `48ef94df838fed59f1995aefa8adb4802d9e20bf`.
  Its five workflows (CI, impact, candidate, native Keycloak, PostgreSQL
  clone-only OCI) completed SUCCESS; no workflow deployed production.
- Official Keycloak 26.8.1 and 26.8.2 synthetic Realm tests each passed
  23/23: native CIMD capability and policy installed, actual Keycloak JVM
  fetched current public ChatGPT metadata and JWKS via fixed-destination
  HTTPS egress, and an exact OAuth authorize request advanced to login.
  The synthetic client UUID, client-jwt/JWKS/PKCE configuration and health
  scope boundary survived a CIMD UPDATE.
- Keycloak 26.8.1 `--db=postgres --features=resource-indicators,cimd:v1`
  clone-only OCI: built, imported a synthetic Realm to PostgreSQL, verified
  OIDC/CIMD discovery, was saved with SHA256 manifest. Production operator
  downloaded it and verified archive/manifest/image ID/amd64, then used
  `docker load` without starting a container. **Tag
  `prp-cimd-pg-clone:26.8.1` is clone-only, not a production image.**
- Existing production backup of the auth Realm previously passed isolated
  PG restore + original Keycloak JWKS public fingerprint + RSA private
  signing/verification. **This does not prove PR #162's CIMD UPDATE on the
  recovered real client/consent.** User explicitly skipped the proposed
  additional merged candidate + real production Realm clone test.
- Production Keycloak has not observed CIMD enabled and current discovery
  did not advertise `client_id_metadata_document_supported`. The real
  ChatGPT /token HTTP 400 yielded
  `CODE_TO_TOKEN_ERROR / invalid_client_credentials` without a specific
  JWT failure reason. Do **not** infer bad signature, audience, JWKS or
  missing token `resource` without evidence.
- Production host's most recent `MemAvailable` around 2,130 MiB and
  Windows Docker Engine unavailable; no authorization to run additional
  services on the production host. There is no proven test environment for
  CIMD + an actual restored production Realm.

## Required release gates, not steps to bypass

1. Obtain owner's **explicit approval for the exact production change**:
   what image, pinned digest, existing containers affected, planned downtime,
   exact Keycloak config/CLI policy diff, backup snapshot, restore test,
   monitoring and rollback mechanism.
2. Validate the clone-only test risk gap or have the owner formally
   accept **in writing** the untested real production UUID/consent migration,
   with a rollback plan preserving database writes and Keycloak key state.
   A prior backup is not a migration test.
3. Produce a **separate, reviewed production image**, with pinned official
   Keycloak 26.8.1 base digest, reviewed PRP health policy and CIMD
   candidate JAR SHA256 hashes, optimized for PostgreSQL, and no synthetic
   Realm/users/keys. Never relabel a clone-only image to production without
   a reproducible build and dedicated acceptance.
4. Preserve **Keycloak runtime feature flags** `resource-indicators,cimd:v1`
   and the exact custom `prp-health-cimd-metadata` provider
   `prp-health-scope-cimd`; the pre-existing
   `prp-production-health-policy` executor must stay in the matched
   exact-ChatGPT policy. The CIMD executor must appear BEFORE the resource
   policy executor. No DCR registration endpoint, public-client downgrade,
   client secret or anonymous fallback.
5. If approved, use documented admin methods to snapshot and diff **all**
   original client policies/profiles, the exact ChatGPT client UUID and
   authenticator/JWKS/PKCE/redirect attributes, optional/default scopes,
   user consent references, Realm signing keys and events settings.
   Never export these secrets or user data to GitHub/CI.
6. Validate `GET /.well-known` metadata on the actual production issuer
   and protected resource; both OIDC and OAuth AS must truthfully advertise
   `client_id_metadata_document_supported=true` only AFTER live CIMD
   policy/JVM tests pass. A JSON-only metadata edit is prohibited.
7. **Operator-driven real ChatGPT connection** against the NEW plugin:
   authorization-code+PKCE S256, OpenAI-managed `private_key_jwt` accepted
   by Keycloak, exact resource audience and `prp.wellness.read`,
   authenticated MCP initialize/tools/list, owner isolation and no
   write scope. Verify refusal cases and real backward-compatible login.
8. Failure rollback needs an **approved transactionally safe** reversion of
   Keycloak image/provider/config/policy and any CIMD-induced DB state,
   with proven restoration of original user consent, client UUID and Realm
   signing material. No blind PostgreSQL volume swap while live writes occur.

## Read-only production discovery probe

This does not change auth, log bodies, request headers or credentials.
Execute from a host with access to the actual production issuer. A transport
failure is **UNKNOWN**, not proof that the server is down. It prints flags
only, never metadata JSON.

```bash
python3 - <<'PY'
import json
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
base = "https://auth.micor.top/realms/prp-mcp-prod"
for suffix in ("/.well-known/openid-configuration",
               "/.well-known/oauth-authorization-server"):
    kind = "OIDC" if "openid-" in suffix else "OAUTH_AS"
    try:
        with urlopen(base + suffix, timeout=7) as r:
            document = json.load(r)
        print(f"{kind}_ISSUER_MATCH=",
              document.get("issuer") == base)
        print(f"{kind}_CIMD_ADVERTISED=",
              document.get("client_id_metadata_document_supported") is True)
        print(f"{kind}_PRIVATE_KEY_JWT_SUPPORTED=",
              "private_key_jwt" in
              document.get("token_endpoint_auth_methods_supported", []))
        print(f"{kind}_S256_SUPPORTED=",
              "S256" in document.get("code_challenge_methods_supported", []))
        print(f"{kind}_DCR_ADVERTISED=",
              bool(document.get("registration_endpoint")))
    except (HTTPError, URLError, ValueError, OSError):
        print(f"{kind}_DISCOVERY_UNAVAILABLE_OR_UNREADABLE=True")
print("PRODUCTION_CHANGED=False")
PY
```

**Release decision: NO-GO.** A successful custom plugin install, synthetic
runner, GitHub action, Docker load, or public metadata check is NOT a real
ChatGPT `private_key_jwt` token exchange. The user must approve any separate
production Keycloak change explicitly.
