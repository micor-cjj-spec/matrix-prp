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
