# Production health authorization candidate

No production installation is authorized by these files. PR #157 remains Draft.
Only `auth.micor.top`, a new `prp-mcp-prod` Realm and independent PostgreSQL volume
are proposed. Existing test Keycloak, databases, Nginx and PRP remain untouched.

## Deliberate registration choice

This candidate **pre-registers** the exact observed ChatGPT metadata URL as its
client ID. It does NOT enable dynamic CIMD and does not claim to fix CIMD parsing.
Keycloak's official MCP guide still documents the metadata-choices incompatibility:
https://www.keycloak.org/securing-apps/mcp-authz-server#_chatgpt_integration

The client ID/callback stay identical to the user's actual requests. Client auth
is only `private_key_jwt`, keys come from the exact official HTTPS JWKS URL, and
PKCE S256/precise redirect/resource/scope remain mandatory. There is no client
secret, public-client fallback, metadata normalizer or anonymous DCR. Changing
registration mode for rollout needs explicit review of this candidate and the
actual ChatGPT connection; a successful synthetic flow is not real ChatGPT proof.

`auth-policy` checks exact authorization parameters and resource/scope on code
exchange and refresh. Keycloak's native signature, PKCE, grant, expiry, rotation
and revocation checks remain. Its condition matches the exact client in only this
Realm, plus explicitly denies DCR; it never uses any-client or domain wildcards.
First-party identity linking uses a separate exact callback and public S256 client;
`none` in discovery describes that client, not ChatGPT's authentication method.

## Isolation and rollout gates

- Production Realm JSON contains no users, keys or secrets. Use first import only;
  never overwrite live Realm data by reimporting. Synthetic users and signing keys
  may be injected only in the disposable CI process, not the image/import artifact.
- Dockerfile has no CA, fixed lab IP, synthetic JWKS or client private key. Base
  and final image digests must be measured/reviewed before installation; tags in
  build defaults are not installation approval.
- Candidate Compose's auth network is internal; only a separately audited exact
  chatgpt.com CONNECT egress service may leave it. The egress image and TLS/DNS/
  SSRF/redirect/key-rotation tests are outstanding until separately evidenced.
  Never run this candidate with an arbitrary proxy image or broaden egress.
- Its only published backend is loopback 18084; PostgreSQL and management ports
  are not published. Secret env files stay root-private 0600; do not print rendered
  Compose or environment values. Docker PostgreSQL non-root volume permissions
  must be rehearsed before accepting the capability-drop candidate.
- `render_auth_nginx.py` only renders an independent exact allowlist vhost. It
  does not change the main site's Host/SNI map. Test against the complete current
  Nginx include set, IPv4/IPv6 and existing services before approval. Do not enable
  extra `www.auth` routing merely because the certificate includes that SAN.
- Fresh production V29 backup and isolated restore remain required. Auth database,
  Realm/users and signing-key backup/restore must be proven before go-live. Videos
  are excluded per the owner's instruction. Configuration rollback must never
  restore pre-V29 SQL over current production.

See `app/docs/technical/production-health-mcp-preparation.md` for data/tool boundaries.
Production enabling requires exact file diffs/hashes, resource budget, verified
images, restoration, current baseline, one controlled Nginx reload/rollback plan,
and explicit approval of that concrete installation. Nothing here starts services.
