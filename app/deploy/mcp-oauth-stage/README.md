# Persistent loopback-only OAuth acceptance lab

This reuses the existing `prp-mcp-stage` backend, MySQL and gateway. It creates
only a separate PostgreSQL 17.6, Keycloak 26.8.0 (same version as CI) and Nginx
TLS container. No production data or credentials; no production reload or DNS
change. Keycloak's CIMD/resource-indicator features remain experimental.

State is `/root/prp-mcp-oauth-stage`; PostgreSQL persists in the dedicated
`prp-mcp-oauth-stage_oauth_pgdata` volume. The original base `.env` is never
overwritten. New credentials are 0600. TLS keys and a private seven-day CA stay
in this directory. The Java truststore contains only public CA certificates.
No TLS certificate checks are disabled. Local test certificates are **not**
publicly trusted and must not be represented as a public HTTPS deployment.

Resource gate before any additional service startup: MemAvailable >= 2 GiB
and root free disk >= 25 GiB. Caps: PostgreSQL 256 MiB, issuer 1 GiB (512 MiB
heap), TLS 64 MiB. Do not run a second PRP backend/MySQL unnecessarily.

## Administrator-only initial preparation

From the already-reviewed isolated staging checkout:

```sh
python3 app/deploy/mcp-oauth-stage/prepare.py
docker compose --project-name prp-mcp-oauth-stage \
  --env-file /root/prp-mcp-oauth-stage/.env \
  -f app/deploy/mcp-oauth-stage/compose.yaml config --quiet
docker compose --project-name prp-mcp-oauth-stage \
  --env-file /root/prp-mcp-oauth-stage/.env \
  -f app/deploy/mcp-oauth-stage/compose.yaml up -d
```

Preparation is exclusive and refuses an existing state directory. Do not rerun
it to replace passwords, signing material or an initialized realm. Realm import
is first-import only, not a migration for an existing authorization database.
Unprivileged Keycloak needs 0755 on its read-only import mount, while its private
parent and `.env` retain 0700/0600. Single-instance cache is explicit; realm keys,
users and sessions persist in PostgreSQL.

## Enable only the isolated test backend

```sh
cd app/deploy/mcp-staging
docker compose --project-name prp-mcp-stage --env-file .env \
  --env-file /root/prp-mcp-oauth-stage/.env -f compose.yaml \
  -f ../mcp-oauth-stage/backend-overlay.yaml up -d --no-build --no-deps backend
python3 ../mcp-oauth-stage/server_e2e.py
```

The overlay enables MCP/OAuth only on this test backend. It cannot change the
database URL/JWT secret and explicitly keeps MCP writes false. The lab's only
published TLS port is `127.0.0.1:18443`; application gateway stays at loopback
18081. Issuer and PostgreSQL have **no** published ports. HTTPS client routing
is local to the test process; SAN/chain validation remains enabled. No host DNS
or system truststore edits are needed.

The runner creates only synthetic users/tasks and records expected/actual HTTP
statuses without response bodies, tokens, cookies or passwords. It stops and
starts only its own issuer for failure/cache/persistence tests. It rotates an
independent test signing key, retaining older verification keys. It never reads
or changes production user records. Reports: `/root/prp-mcp-phase2-evidence`.

Access JWT lifetime: 60 seconds, with the resource verifier's existing 60-second
clock skew. Refresh rotation is on, max reuse 0; session idle 600 seconds / max
1800 seconds, no offline scope. IdP logout/revocation prevents subsequent refresh
but a previously signed stateless access JWT can remain valid until expiry.
PRP client-grant revocation is checked on every request and denies immediately.
Unknown keys/JWKS failure must not become authenticated. Cached known valid keys
can continue within their original token lifetime during issuer outages.

Keep old verification keys for at least the maximum access-token lifetime plus
clock skew and propagation delay; never immediately delete keys to simulate
revocation. This lab deliberately leaves historical verification keys present.

## Return the base test backend to MCP/OAuth OFF

```sh
cd app/deploy/mcp-staging
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml \
  up -d --no-build --no-deps backend
```

To stop the issuer/TLS laboratory while preserving all state:

```sh
docker compose --project-name prp-mcp-oauth-stage \
  --env-file /root/prp-mcp-oauth-stage/.env \
  -f app/deploy/mcp-oauth-stage/compose.yaml stop
```

Never use `down -v`, delete volumes, or apply these commands to a production
project. Inspect the selected project and rendered service set before executing.

## Public access remains pending

`public_nginx.py` produces review-only vhosts outside `/etc`. Public DNS for
`prp-test.micor.top` and `auth-test.micor.top`, publicly trusted certificates,
access policy and explicit authorization are required **before** installing or
reloading any production Nginx configuration. Local syntax validation using
test certificates does not validate an absent public certificate or DNS record.

Copy the exact ChatGPT management-page callback and client metadata URI when
actual account eligibility and connection mode are verified. Never allow wildcard
redirects. Current official authentication/connection requirements:
https://developers.openai.com/plugins/build/auth and
https://developers.openai.com/plugins/deploy/connect-chatgpt .

The lab uses an explicitly registered PKCE probe, not a registered ChatGPT
connection. The isolated issuer network intentionally has no general outbound
Internet path; public CIMD document fetching needs a separately reviewed egress
policy. A Plus subscription alone does not prove the user's connection permission.


## Existing-V2 public cutover and shared-Realm restore gate (operator report 2026-10-25)

This is an operator-reported state, not a general instruction to publish MCP.
The independently isolated V2 deployment uses `prp-mcp-v2`, the dedicated
`matrix_prp_mcp_stage_v2` schema, a loopback gateway on `127.0.0.1:18082`,
and a source checkout pinned to `f8a154474053bfb705d81a9d0da9f81df12d5194`.
The legacy stage `18081` and old Flyway V24 lineage remain intact.
On 2026-10-25, the two exact *test-only* public Nginx routes
`/api/mcp` and `/.well-known/oauth-protected-resource/api/mcp`
were reported switched to `18082`: resource metadata returned 200 with
`prp.tasks.read` only, and unauthenticated initialize returned an expected 401
with the canonical Bearer resource-metadata challenge. The production
`matrix-prp.service` remained active. This is not a ChatGPT login test.

### Still blocked: active Keycloak test Realm mapper

The already-imported test Realm still uses the older `prp-pkce-probe`
`oidc-audience-mapper`: `included.client.audience=matrix-prp-mcp-resource`.
V2 expects an access-token audience of the *exact HTTPS resource*:
`https://prp-test.micor.top/api/mcp`.

The draft-branch `build_realm.py` **now** emits
`included.custom.audience=<exact resource>`, with no
`included.client.audience`. The generated realm import affects **fresh**
Keycloak instances only: editing this script does **not** update a populated
Realm. Disposable GitHub Actions tests exercise persisted mapper validation,
a synthetic legacy-mapper repair and restoration, and PKCE/user-link/MCP
round-trips. Those tests are not evidence of live Keycloak safety.

The operator generated these private, read-only review files:
`/root/prp-mcp-backups/v2-keycloak-mapper-review-oyp642m6/original.json`
(SHA256 `80834a6ea75b99a504e06e6a218af7215814475bcbecd00b932973e8e6672ca6`)
and `candidate.json`
(SHA256 `a26b7ec0f1739d2d12cd948f6134410b91a2782fdc4ea970036ef1bc1c4eb44b`).
The candidate changes only the two audience config fields and retains the
mapper UUID. On last inspection the active mapper matched the backup exactly.

**Do not PUT this candidate into the shared active Realm yet.** The existing
`prp-mcp-oauth-stage_oauth_pgdata` named Postgres volume serves the legacy
stage, with other existing clients to preserve. A recovery inventory is
*not* a restore test. The prior guard expected the genuine evidence files
`/root/prp-mcp-cimd-stage-b/host-guard/approved-install.safe.json` and
`fresh-b2-restore.safe.json`; both were absent at last inspection. Do not
fabricate/copy receipt JSON to pass a guard, bypass Keycloak issuer signing-key
recovery checks or mutate production Nginx to work around the failure.

For read-only preparation on the server, inspect only file existence, sizes,
permissions and timestamps for real backup artifacts, plus the Keycloak
Postgres volume/mount and free memory/disk. **Do not treat a running database,
a `pg_dump` file, or an old CI report as completed recovery proof.** Next,
on a *separately named, loopback-only* restore environment, verify the
restored Realm has the correct client inventory, mapper and signing key
fingerprints. Apply the candidate exclusively inside that clone; verify
its signed JWT audience and reverse the mapper change before any guarded
live test-stage operation. Preserve the old image, schema and volume.

The public `/api/mcp/link` path was still deliberately 404; local V2
unauthenticated POST returned 401. Avoid broadly exposing `/api/**`.
Identity linking and a real client grant on V2's separate, synthetic test
database remain unverified. Real ChatGPT support further requires exact-client
PKCE/private-key-JWT interoperability; the known Keycloak refresh-resource
negative test in PR #113 remains a blocker for `offline_access`. Keep writes
disabled, do not merge this Draft PR into `main`, and do not claim live PRP
data connectivity from discovery/CI alone.
