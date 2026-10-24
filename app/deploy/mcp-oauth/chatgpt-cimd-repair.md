# ChatGPT CIMD repair: verified blockers and next gates

This is a diagnosis and change-preparation record, not an installation approval.
No production configuration, Realm, database, SSH trust file or write flag was
changed by these checks. Never replace the installed controller or invent gate
receipts to apply this document.

## 2026-10-24 observations

- Independent administrator-console ED25519 measurement matches the presented
  server key: `SHA256:NOEkvKq3BcBnErn+vjNMyjPaEt21xXLUJptsK9HXX64`.
  Windows known_hosts contains different ED25519 and ECDSA keys. Their original
  provenance and the reason for replacement are not established. Current public
  key files report modification time 2026-10-09 06:21 UTC; timestamps alone do
  not establish reinstall or IP migration.
- Authenticated, internal, GET-only Realm inspection returned empty profiles
  and policies. There are 13 clients; the exact ChatGPT client is absent.
- Active Keycloak has `KC_FEATURES=cimd,resource-indicators`, fixed hostname
  `https://auth-test.micor.top` and `KC_PROXY_HEADERS=xforwarded`. No hostname-admin
  override was present. The reviewed custom provider image remains stopped.
- A new authorization request using S256, a fresh state and the exact callback
  and resource returned HTTP 400 containing `Client not found`, no login form.
  No user authenticated and no authorization code/token was exchanged.
- Public discovery and issuer JWKS returned 200; `/admin/` and master discovery
  returned 404. Unauthenticated MCP POST initialize returned 401 with a Bearer
  challenge. Backend `MATRIX_PRP_MCP_WRITE_ENABLED=false` was confirmed.
- Official CIMD was fetched from the server host with HTTP 200. This does not
  establish the active Keycloak container's egress or client-assertion validation.
- Keycloak and PostgreSQL have no published host ports. The actual local TLS
  gateway listens at 127.0.0.1:18443. Nothing listens at port 18080.
- Internal `/admin/master/console/` returned 200, but its HTML references the
  fixed public hostname. A plain HTTP port-forward to 18080 is therefore not a
  demonstrated usable browser console. Authenticated internal Admin REST GETs
  already work, with credentials/tokens retained only inside the server process.
- The existing OAuth cutover controller's `--check` returned exit 2,
  `PRODUCTION_NGINX_GUARD_NOT_INSTALLED_OR_DRIFTED`. Do not PUT Realm policies or
  start a different cutover to evade this gate.
- Production PRP PID 1770191 and Nginx PID 2222545 remained active, NRestarts=0.
  Nginx SHA256: micor.top.conf
  `ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b`;
  prp-mcp-test.conf
  `be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d`.
  No production database connection was made by these diagnostics.

## Actual client metadata and scope changes requiring review

The official document identifies:

- client ID: `https://chatgpt.com/oauth/client.json`
- redirect: `https://chatgpt.com/connector_platform_oauth_redirect`
- JWKS: `https://chatgpt.com/oauth/jwks.json`
- legacy token authentication preference: `private_key_jwt`
- methods supported during the transition: `none`, `private_key_jwt`.

Do not impose private_key_jwt on unrelated clients. For this actual document and
the current server's advertised intersection, the legacy preference selects
private_key_jwt. The server still must verify the real OpenAI assertion; a
synthetic assertion passing a separate CI fixture cannot prove that.

The existing strict provider source
`0ec73540b9bbd5ff4c467f9e7177cd882a776f75f49494eb01779bcb266a8cf5`
accepts only the literal scope `prp.tasks.read`, rejecting openid/offline_access.
It cannot be deployed unchanged for the newly requested three-scope flow.
Review the provider, optional scopes, consent and offline-session/refresh
rotation/revocation together. Preserve exact client ID, callback, S256,
resource/audience, SSRF restrictions and direct-DCR refusal. Never just enable
every Realm default scope; financial, wellness and all write scopes stay denied.

The built-in Keycloak executor is `client-id-metadata-document`, with condition
`client-id-uri`, associated through an enabled policy/profile. The historical
strict candidate uses different custom provider IDs. Do not configure custom
IDs before their reviewed JAR is installed, or replace exact-client constraints
with an unrestricted domain or anonymous registration policy. The logo host
`persistent.oaistatic.com` is not an allowed client-ID or callback origin.

## Windows: update only after the independent identity check

The commands below do not run automatically. They verify the scanned ED25519
key against the independently confirmed value before changing any trust file.
Do not use StrictHostKeyChecking=no or accept an unverified alternate algorithm.

```powershell
$expected = 'SHA256:NOEkvKq3BcBnErn+vjNMyjPaEt21xXLUJptsK9HXX64'
$knownHosts = Join-Path $env:USERPROFILE '.ssh\known_hosts'
$scanFile = Join-Path $env:TEMP ('prp-host-' + [guid]::NewGuid() + '.pub')
ssh-keyscan -T 10 -t ed25519 207.57.123.94 2>$null | Set-Content -Encoding ascii $scanFile
if ($LASTEXITCODE -ne 0) { throw 'Host-key scan failed; trust unchanged' }
$fingerprint = ssh-keygen -lf $scanFile -E sha256
if ($LASTEXITCODE -ne 0 -or @($fingerprint).Count -ne 1 -or
    ($fingerprint -split '\s+')[1] -cne $expected) {
    throw 'Host fingerprint mismatch; trust unchanged'
}
Copy-Item -LiteralPath $knownHosts -Destination ($knownHosts + '.backup-' + (Get-Date -Format yyyyMMdd-HHmmss))
ssh-keygen -R 207.57.123.94 -f $knownHosts
if ($LASTEXITCODE -ne 0) { throw 'Update failed; restore backup' }
Get-Content -LiteralPath $scanFile | Add-Content -Encoding ascii -LiteralPath $knownHosts
Remove-Item -LiteralPath $scanFile
ssh -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 root@207.57.123.94
```

Do not reuse the obsolete port-18080 tunnel. For a browser console, prepare a
separate internal TLS gateway that binds only loopback, retains the fixed
auth-test hostname and proxies required admin/master/static paths only internally.
Use a verified SSH forward and an isolated browser DNS mapping. First review
certificate paths, available ports, Host/SNI, backup/recovery and rollback;
never expose `/admin/` publicly or change the issuer to localhost. This gateway
has NOT been installed or tested by this PR.

## Next transaction and acceptance

1. Review the collector optimization and delivery-time budget; obtain a new,
   explicitly bounded WARP authorization if required. All previously approved
   attempts have been consumed. No automatic new registration or transaction.
2. Obtain fresh, isolated backup-recovery proof. Complete the existing Host/SNI
   install/public acceptance and business-login gates, or stop/roll back.
3. Review and rehearse the three-scope provider/profile change on a restored
   private clone, including offline refresh, expiry, replay and revocation.
   Save original image, policies/profiles, mappers and client state; verify
   rollback independently. Keep the 13 legacy clients intact.
4. Only after the cutover gate passes, apply the separately reviewed test-only
   OAuth update. Preserve public Nginx/admin denial, production app/database and
   write flag. No merge of PR #95.
5. In ChatGPT, reconnect PRP at `https://prp-test.micor.top/api/mcp` with a new
   authorization request. Confirm the auth-test login page, grant only
   `openid offline_access prp.tasks.read`, bind the synthetic PRP user, discover
   tools and invoke `prp_tasks_list`. Never share code/state/token/cookies.
6. Verify actual signed token claims and user isolation internally. Revoke PRP
   client authorization and prove the old access token is immediately rejected.
   Record each layer separately; discovery or CI is not real ChatGPT acceptance.

## Reusable read-only preflight

`python3 app/deploy/mcp-oauth/chatgpt_cimd_preflight.py` fetches only three fixed
HTTPS documents, with default certificate checking, no proxies or redirects,
bounded JSON and duplicate-key rejection. It checks exact official client and
callback, method intersection and public RS256 JWKS availability. Any transport
failure is UNVERIFIED, never safe denial. A pass remains metadata-only and does
not prove container egress, Realm policy, login, JWT validity or tool use.

References: [Keycloak MCP setup](https://www.keycloak.org/securing-apps/mcp-authz-server),
[OpenAI OAuth](https://developers.openai.com/plugins/build/auth),
[official client document](https://chatgpt.com/oauth/client.json).

## P0 follow-up: precise live gate diagnosis, 2026-10-24 23:07 CST

The original `verify_evidence()` returned ISOLATED_GUARD_EVIDENCE_PASSED.
The exact first failing live condition compares the ordered Nginx inventory
and six source-file SHA256 values. Four files match. The two mismatches are:

| File | Actual rollback baseline SHA256 | Required candidate SHA256 |
| --- | --- | --- |
| micor.top.conf | ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b | da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b |
| prp-mcp-test.conf | be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d | 90814118bda4c8ca0be3d87ae36accb003a4be7f593954d552bfe05c1c98e6bd |

These are the known original rollback bytes, not an unexplained third version.
The candidate hashes agree with the already-reviewed guard transaction. No
controller logic, expected digest, certificate or production route was edited.

There are also two independent downstream blockers: both
`host-guard/approved-install.safe.json` and `host-guard/fresh-b2-restore.safe.json`
are absent. The first needs actual completed public acceptance and the installed
six-file inventory; the second needs actual isolated restore/fingerprints/signing
key checks within one hour and the matching dump under the approved backup root.
Neither can be made valid by copying old evidence or setting boolean fields.
The original guard coordinator deliberately reports `b2_execution_ready=false`;
its state alone is not a substitute for these B2 handoff/recovery requirements.

An additional isolated mirror check tested both the current baseline and the
exact two-file candidate with the server's actual Nginx binary: both `nginx -t`
exits were 0. Only include/log/PID paths were redirected to the private mirror;
public certificate paths were preserved. Mirror result:
`/root/prp-p0-syntax-omwnbycj/result.safe.json`. All six production file hashes
were unchanged. No Nginx configuration was loaded or reloaded.

The minimal live repair remains the existing controlled two-file installation,
not a controller change. Before it may run: fresh config/database recovery
proof, exact candidate/source pins, isolated syntax, explicit transaction
authorization and genuinely fresh required external evidence must all pass.
Forward failure must restore the two verified original files through the same
controller and complete fresh rollback acceptance. The old direct installer
explicitly disables `--install`; do not call another Admin REST/installer entry
to work around this. Once real installation/acceptance and recovery receipts
exist, rerun the original command:

```sh
python3 /root/prp-mcp-cimd-stage-b/cutover_b2_guarded.py --check
```

No new WARP registration is authorized by this PR. All existing attempts were
consumed. The full baseline diagnostic exceeded the unchanged 300-second gate;
the TLS-context candidate passed isolated tests but has not proved full public
freshness including evidence delivery. Do not begin a production transaction
or label P0 complete on that basis.

## Scope discovery correction (source change, not deployed)

`McpOAuthMetadataController` previously advertised its full static scope catalog
regardless of the write switch. The live PRM also lists financial, wellness and
write scopes. This is a concrete source of excessive client scope requests;
the actual client request and any saved ChatGPT scope selection must still be
rechecked after rollout and metadata refresh.

Discovery now defaults to exactly `prp.tasks.read`. Explicit opt-in is available
through `MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES` (comma separated). Unknown,
empty, duplicate and wildcard entries are startup errors; write scopes also
require the independent write switch. The complete catalog remains unchanged
for existing grant validation: metadata is a client-request hint, not a substitute
for issuer/token/grant/tool authorization. `openid` and `offline_access` are
authorization-server scopes, not PRP tool scopes, so they do not belong in this
resource allowlist. Their Provider/consent/refresh behavior still needs the
separate gated three-scope repair described above.

Regression coverage checks the actual public MockMvc endpoint returns exactly
one scope, requires opt-in for financial discovery, and rejects invalid scope
configuration or write advertisement with writes disabled. Nothing in this
change enables writes, modifies any stored grant, or deploys an application.


## CIMD PKCE event-scope compatibility — Keycloak 26.8 review gate

Keycloak upstream issue [#52795](https://github.com/keycloak/keycloak/issues/52795)
(documented 2026-09-15; 26.8.0 workaround reported 2026-10-06)
warns that a `pkce-enforcer` executor attached **only** to the
`client-id-uri` CIMD policy may not execute on the client registration,
authorization or token events. The policy may look enabled while authorization
codes can be issued without an S256 code challenge. Treat this as an
explicitly unverified security risk for this staging Keycloak, not a proven
live exploit or evidence of a fixed 26.8 deployment.

Additional REQUIRED isolated-restored-Realm acceptance before allowing a
ChatGPT login or deploying the CIMD policy:

1. Keep the allowlisted `client-id-metadata-document` CIMD resolver Profile
   and HTTPS `client-id-uri` Policy limited to `chatgpt.com`, with exact
   verified callback, JWKS, resource indicator and scope permissions.
2. Do **not** place PKCE enforcement only in that URI-matching Policy. Review
   a **separate** `pkce-enforcer` Profile with `auto-configure=true`, and a
   matching policy whose condition applies on CIMD client registration,
   such as `client-updater-context` with
   `update-client-source=["ByAnonymous"]`. The Keycloak issue reports
   this workaround working on 26.8.0, but the exact installed build must
   be tested. Do not accidentally broaden permissions to unrelated clients.
3. On an ephemeral/fully-restored isolated Keycloak with the exact provider
   version, send **new** authorization requests with (a) missing
   `code_challenge`, (b) `code_challenge_method=plain` and
   (c) a valid S256 challenge. Cases (a)/(b) MUST fail and case (c) MUST
   proceed only with registered exact ChatGPT client/redirect/resource.
   Check both the first CIMD resolution and subsequent cached-client request.
4. Verify authorization-code exchange refuses absent/incorrect
   `code_verifier`, and that the saved Keycloak client requires S256.
   Also test callback mismatch, unrelated client host and unregistered
   resource denial. Verify older 13 clients remain unchanged.
5. Persist only sanitized results and the true active policy/realm hashes;
   never copy an upstream demonstration policy to production without the
   original guarded host change-control approvals and fresh recovery evidence.

The current PR has **not** installed either policy or performed these
negative live tests. Passing external metadata checks and disposable PKCE
tests for a **pre-registered** client cannot satisfy this CIMD-specific gate.

## Disposable Keycloak 26.8 exact-client pre-registration results (2026-10-24)

A new isolated GitHub Actions test, `ci_chatgpt_cimd_pkce.py`, runs **only**
against the short-lived Keycloak container. It installs test-only CIMD
Profile/Policy records and uses the actual ChatGPT public client ID
`https://chatgpt.com/oauth/client.json`. On the native CIMD path it
reproducibly encounters HTTP 400 with Keycloak's
`UnrecognizedPropertyException` for
`token_endpoint_auth_methods_supported`. This corroborates upstream
Keycloak's documented compatibility limitation. **Do not weaken JSON parsing,
change ChatGPT metadata, trust arbitrary CIMD domains or call that path
accepted.**

A distinct **exact-client pre-registration** alternative then succeeds
in the same disposable Realm **only after disabling the generic CIMD URI
interception policy**. It registers exactly one confidential client with:
- Client ID equal to the official ChatGPT metadata URL, exact OAuth
  redirect `https://chatgpt.com/connector_platform_oauth_redirect`,
  `clientAuthenticatorType=client-jwt`, official JWKS URL, and S256
  explicitly required.
- Authorization Code only, no implicit/password/service-account grant;
  empty web origins, consent required, full-scope access disabled, and
  task-read only as optional PRP scope.

[Green isolated evidence](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40108559013)
shows a valid S256 request proceeds to the Keycloak login page, while
requests missing PKCE or using `plain` are rejected. Exact client
identity, redirect and stored S256 requirement are read back via the
**disposable** Admin REST API. No user login, authorization code,
`private_key_jwt` assertion, token endpoint exchange, refresh grant,
PRP identity-link, real ChatGPT account, or MCP tool request was tested
with this static client. Those remain HARD gates.

This demonstrates a narrower possible alternative to a custom CIMD
executor, **not** authorization to modify the active test Realm.
The active Realm has 13 clients and its client policies must be preserved.
Before any authorized test-only change:
1. Obtain genuine, fresh B2 backup/restore + reviewed Nginx guard evidence
   and an approved change transaction through the existing controller.
2. Evaluate the exact-client pre-registration plan in a restored isolated
   Keycloak clone; determine client JWT assertion compatibility with a
   controlled test key, then with a real ChatGPT-originated token request.
3. Recheck OIDC scopes (`openid offline_access prp.tasks.read`), resource
   indicator/audience, signed client identification, refresh rotation,
   revoke/expiry, account linkage and task-read isolation end-to-end.
4. Never replace the active Realm's complete Clients/Policies collections
   with the disposable CI examples or silently disable active policies.
   If the original controller cannot safely apply this alternative,
   leave production unchanged and record the blocker.

The earlier CIMD-specific PKCE policy test is still required **if CIMD
remains the chosen mechanism**; successful static pre-registration does
not prove dynamic CIMD interoperability.


## Offline refresh resource-indicator negative test — deployment blocker

The disposable Keycloak 26.8 authentication test at
[run 40111110684](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40111110684)
successfully exercised a synthetic (not ChatGPT) confidential client:
real login/consent, PKCE S256 authorization-code exchange, signed
`private_key_jwt`, an RSA-verified JWT with exact PRP MCP URI audience,
`offline_access` refresh, rotated refresh tokens, replay denial and
refresh-token revocation. The Keycloak Audience mapper must use
`included.custom.audience` with the exact MCP HTTPS URI, **not**
`included.client.audience`, because Keycloak's built-in mapper ignores
custom audience when a client audience is populated.

However, an additional fail-closed negative test in
[run 40111254877](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40111254877)
proved that a synthetic OAuth client refreshing with an **unapproved**
`resource` URL received HTTP 200 instead of `invalid_target`. A fixed
custom audience mapper can still stamp the PRP URI on the new JWT.
This is an **authorization-server resource-indicator enforcement gap**
for the tested Keycloak 26.8 configuration. The positive test is not
an RFC 8707 refresh-grant compliance proof. The negative regression is
intentionally retained separately in draft PR #113 rather than hidden
or weakening the client/resource checks. RFC 8707 applies the
`resource` parameter to all access-token request grant types.

**Do NOT activate offline refresh for real ChatGPT or release MCP** based
on the positive test alone. Require a distinct authorization-server
upgrade, compatible provider, or strictly reviewed Keycloak extension
that enforces the exact resource on refresh grants, and rerun the
negative test on an isolated restored Realm. Never make PRP accept
`matrix-prp-mcp-resource` as a substitute for its canonical URL,
skip refresh resource constraints, or confuse JWT signature/audience
checks with the authorization-server grant validation.

## Exact ChatGPT static-client scope and audience contract — isolated proof

[Disposable Keycloak 26.8 run #40112710941](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40112710941)
verified two previously missing requirements in the **exact-client
pre-registration** fallback fixture (no real ChatGPT private signing key):

- The generated Realm may lack the built-in `offline_access` scope because
  it imports explicit client scopes. A reviewed administrator must ensure the
  scope exists, and the exact confidential ChatGPT client must allow **both**
  `offline_access` and `prp.tasks.read` as optional scopes, not just
  task-read. The isolated authorization probe sends the exact minimum:
  `scope=openid offline_access prp.tasks.read`; valid PKCE S256 reaches the
  login stage, missing/plain PKCE are rejected.
- For the MCP bearer, the audience mapper must use
  `included.custom.audience=<exact full HTTPS MCP resource URI>`.
  `included.client.audience=matrix-prp-mcp-resource` denotes an internal
  Keycloak client ID instead of the external MCP resource, which can break
  token validation after refresh. The isolated test reads back the persisted
  exact-URI mapper and RS256 client JWT settings.

The test configures and checks those properties **only in its disposable
GitHub Actions Realm**. It does not edit active client registrations, mint
tokens signed by ChatGPT, perform a real account link, or issue a guarded
staging release. Retain the existing B2 recovery/Nginx safety gates and
client-policy change control.

## Live-public metadata scope mismatch — read-only probe, 2026-10-24 18:12 UTC

The external, unauthenticated GitHub Actions runner checked only two exact
public HTTPS GET endpoints. There were **no OAuth credentials, login, admin
calls, tokens, data modifications, Nginx changes or Keycloak PUTs**.

- [Read-only probe #40119639867](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40119639867):
  the Keycloak OIDC discovery endpoint passed exact issuer, S256 and token
  endpoint checks.
- The live public RFC 9728 protected resource at
  `https://prp-test.micor.top/.well-known/oauth-protected-resource/api/mcp`
  returned the expected resource and issuer, **but advertises additional
  write, finance, and wellness scope categories** rather than only
  `["prp.tasks.read"]`; the probe correctly exited nonzero.
- This **does not establish those tools can be invoked or any write is enabled**
  or reveal why the running backend differs from source defaults. It is a
  public discovery mismatch, **not** production readiness or a reason to
  widen requested scopes. The running build/env and server receipts are
  unverified via GitHub.

Reproduce without credentials from a trusted network or isolated CI runner:

```sh
python3 app/deploy/mcp-oauth/ci_public_readonly_probe.py
```

This fixed-host, read-only checker permits no redirects or HTTP proxies,
validates server TLS, bounds JSON and prints only recognized status categories.
Exit 0 requires **both** strict task-only public scope metadata and expected
Keycloak OIDC discovery. Any network error is `UNVERIFIED`, not proof the
server is down. It never verifies actual OAuth tokens, Realm policies,
the Nginx guarded-install receipt or B2 recovery.

Do **not** attempt a production reload or test Realm change solely to fix
discovery. After existing independent B2 restore/Nginx/Keycloak approvals
allow a staged change, repeat the checker, independently verify the MCP
write switch and PRP owner grant isolation, then perform real authorized
ChatGPT OAuth and `prp_tasks_list` acceptance. PR #95 remains Draft.
