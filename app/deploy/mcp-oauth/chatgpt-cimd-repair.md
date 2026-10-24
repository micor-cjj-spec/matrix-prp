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
