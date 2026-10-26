# B2: evidence inventory and no-go until an independent approval

Status as of 2026-10-26: **NO-GO for any shared-Keycloak installation,
public Nginx change, `main` merge or production PRP MCP activation.**
No GitHub Actions artifact, host script, synthetic OAuth client or admin
REST response may replace an explicitly approved live change transaction.

## Technical work already demonstrated

The operator-reported, SHA-pinned script at commit
`c79f6515d2611ce0d77a8901808a01be896242d7`
restored a disposable **101-table PostgreSQL** snapshot and started a
separate Keycloak **26.8.0** with an exact-client configurable
Client Policy SPI. Original **13 OAuth clients** survived unchanged.
Issuer signing public keys matched the active Realm; the audience mapper
was exercised and rolled back. Signed synthetic task-read tokens,
correct-resource refresh, rotation/replay denial, revocation,
foreign/duplicate/blank resource denial and finance-scope escalation
denial all passed. Synthetic user and policies were removed, clone
resources cleaned, V2 HEAD unchanged, script exit 0.

This is **not** evidence of a production ChatGPT OAuth connection.
The restored clone used a synthetic password grant to get its first
refresh token; independently tested Authorization Code + PKCE +
`private_key_jwt` is only CI evidence, not a real ChatGPT session.

## B2 independent installation / recovery evidence

The pre-existing operator gate expects the following named receipts
**on the host**, both last reported missing; these exact paths follow
`app/deploy/mcp-oauth-stage/README.md`:

- `/root/prp-mcp-cimd-stage-b/host-guard/approved-install.safe.json`
- `/root/prp-mcp-cimd-stage-b/host-guard/fresh-b2-restore.safe.json`

Never generate, copy, reuse or invent receipts to make the guard pass.
Only the actual independent installer/recovery reviewer or approved gate
should supply them after authentic approval and recovery verification.
File presence, permissions, and timestamps do not independently prove
provenance, scope, freshness or acceptance. A prior recovery run on an
ephemeral Realm **does not auto-issue** a B2 recovery receipt.

`b2_evidence_inventory.py` checks only lstat metadata for the two
specific expected files, their parent directory and the known backup
artifact. It refuses symlinks and unsafe metadata but **always** says
`deployment_permitted: false` and
`b2_authorization: BLOCKED_UNTIL_INDEPENDENT_REVIEW`, even when both
files are present. It never opens their contents, prints credentials,
writes JSON, alters Nginx, reads the live Realm or contacts MySQL.
The CI tests verify no fake file can change that decision.

### Operator-only read-only command (after review)

Use a pinned GitHub commit from PR #113, keeping the V2 worktree as-is:

```sh
V2=/root/matrix-prp-mcp-v2-staging
PIN=REPLACE_WITH_VERIFIED_FULL_PR113_HEAD
FILE=app/deploy/mcp-oauth/keycloak-resource-guard/b2_evidence_inventory.py
git -C "$V2" fetch --no-tags origin test/mcp-authcode-privatejwt-refresh-20261024
test "$(git -C "$V2" rev-parse FETCH_HEAD)" = "$PIN"
git -C "$V2" show "$PIN:$FILE" | python3 -
```

The output is a read-only inventory; **it is not an install approval**.
Do not post receipt contents or secrets to GitHub. If the receipts remain
missing or have unsafe permissions, stop. Do not execute any live
Keycloak Admin REST write or Nginx reload.

## Remaining independent release gates

1. Verify actual B2 change authorization and a separate freshly completed
   recovery gate using their original approver and signing/provenance
   checks; no automatic conversion of clone CI into approval.
2. Review exact candidate JAR SHA, policy targeting, `client-attributes`
   condition and the mapper diff; document restore and *reversible*
   downgrade on the active test Realm, with 13-client safety checks.
3. Review exact public DNS/TLS, Host/SNI/Authority, Nginx allowlist
   (only the necessary `/api/mcp/clients/pairing` and identity-link
   routes, not `/api/**`), canonical resource and issuer metadata.
4. Separately confirm this ChatGPT account is entitled to configure the
   custom MCP connection, the actual callback and registration method,
   and that its real refresh request is compatible with the authorization
   server resource policy; do not assume behavior from synthetic clients.
5. Real owner-authorized PRP test-user pairing, authenticated read-only
   `prp_tasks_list`, wrong-user denial and revocation. Keep write tools
   disabled, do not merge Draft PR #95/#113 or deploy production until
   a separate explicit release decision.

This document deliberately provides **no installation command**.
