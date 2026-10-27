# PRP MCP — isolated staging deployment (PR #95)

**Not a production deployment.** All Docker Compose ports are bound to `127.0.0.1`. The staging MySQL volume `stage_mysql`, schema `matrix_prp_mcp_stage`, accounts and secrets are separate from production `matrix-mysql / matrix_prp`. OAuth Keycloak runs as a second, separate Compose project. This directory contains *infrastructure source only*: running it requires explicit operator access to a host and public TLS/DNS.

## 1. Prepare the isolated host

Use an empty staging VM or a separately administered host. If co-locating with the real PRP, **do not change** the existing `matrix-prp.service`, Nginx `micor.top` server block, `/var/www/prp`, `/var/lib/matrix-prp-deploy`, `matrix-mysql`, or port `11000`. No production database snapshot, mounted data folder or existing secrets are used.

Choose these operator-controlled DNS hostnames pointing to the *staging* TLS gateway:

- `prp-test.micor.top` — staging Web `/prp/`, OAuth protected API `/api/mcp`.
- `auth-test.micor.top` — staging Keycloak `/realms/prp-mcp`.

Prepare **independent** TLS certificates for both hostnames. Do not infer availability of DNS records or TLS from a GitHub CI run.

Work on the review branch in a **separate checkout**, not the running production workspace:

```bash
git clone --branch feat/prp-mcp-gateway-v1 --single-branch https://github.com/micor-cjj-spec/matrix-prp.git matrix-prp-mcp-staging
cd matrix-prp-mcp-staging/app/deploy/mcp-staging
python3 prepare_env.py --stage-host prp-test.micor.top --auth-host auth-test.micor.top
python3 check_env.py --env-file .env
```

The generator writes `.env` as mode **0600** and displays **no passwords**. Record the generated staging administrator password securely for browser login; do not paste it into ChatGPT. **Never commit either project's .env.** The generator refuses to overwrite existing secrets.

## 2. Configure Keycloak as a separate authorization server

```bash
cd ../mcp-oauth
python3 build_realm.py \
  --resource https://prp-test.micor.top/api/mcp \
  --staging-client-id prp-pkce-probe \
  --staging-redirect http://127.0.0.1:8765/callback
```

Create `app/deploy/mcp-oauth/.env` from that directory's `.env.example`, using freshly generated secrets **different** from the PRP staging secrets. Set `MCP_AUTH_PUBLIC_URL=https://auth-test.micor.top`. Validate the issuer's DNS/TLS setup and review the generated first-import realm. Only after the isolated Keycloak configuration is reviewed, run:

```bash
docker compose --project-name prp-mcp-auth --env-file .env -f compose.yaml config --quiet
docker compose --project-name prp-mcp-auth --env-file .env -f compose.yaml up -d
```

This exposes Keycloak only on **`127.0.0.1:18080`**. Its PostgreSQL is not shared with PRP's MySQL or the PRP staging MySQL. The Keycloak realm import executes only on first creation; never assume an existing realm is updated on restart.

## 3. Start PRP staging **with MCP still OFF**

```bash
cd ../mcp-staging
python3 check_env.py --env-file .env
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml config --quiet
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml up -d --build
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml ps
```

The backend image is **built from the branch source** using Java 21 and Maven. The Web image is built with `VITE_APP_BASE=/prp/`. Staging MySQL starts with a **brand-new empty volume** and `MATRIX_PRP_FLYWAY_ENABLED=true`. Existing historical and V24–V27 migrations apply **only to this empty staging database**, never to the production schema.

PRP staging gateway listens only on `127.0.0.1:18081`. Before applying any external TLS proxy, test with an explicit staged Host:

```bash
curl -fsS -H 'Host: prp-test.micor.top' http://127.0.0.1:18081/api/health
curl -I -H 'Host: prp-test.micor.top' http://127.0.0.1:18081/prp/
```

API readiness may need a separate check if `/api/health` is not public in your deployment; inspect only the staging service logs: `docker compose --project-name prp-mcp-stage --env-file .env logs --no-color backend`. Never publish bootstrap credentials, tokens or sensitive headers in CI logs.

## 4. Attach TLS to only the two staging hostnames

Have your existing trusted Nginx or TLS gateway proxy these **dedicated** test server blocks:

- `https://prp-test.micor.top/*` → `http://127.0.0.1:18081`
- `https://auth-test.micor.top/*` → `http://127.0.0.1:18080`

Preserve exact public Host and `X-Forwarded-Proto: https` on **both** origins; reject unrecognized Host headers in the default TLS server. Configure DNS, valid certificates and gateway controls using your normal infrastructure process. **Do not replace the production `micor.top` Nginx vhost**. The PRP staging gateway routes `/prp/` to its built Web files, `/api/` to staging Java, and `/.well-known/oauth-protected-resource/api/mcp` to staging Java; avoid the wrong `/prp/api/mcp` prefix.

Only expose these two staging hostnames after HTTPS/cert and restricted admin access have been reviewed. Test data should be fake and safe to discard.

### TLS vhost generator (review only)

From the isolated staging checkout, after generating the private `.env` and **after** creating trusted certificates for both staging names:

```bash
cd app/deploy/mcp-staging
python3 check_env.py --env-file .env
python3 render_tls.py --env-file .env --output .generated/staging-tls.conf
```

Review `.generated/staging-tls.conf` before any privileged action. It creates precisely two separate HTTPS vhosts:

- `prp-test.micor.top` → **127.0.0.1:18081**, preserving `/prp/`, `/api/` and RFC 9728 discovery paths.
- `auth-test.micor.top` → **127.0.0.1:18080**, with public `/admin/`, `/realms/master/`, health and metrics paths denied. Authenticate as admin only through a separately secured operator channel such as VPN or an authenticated SSH tunnel.

The generated configuration references **existing** `/etc/letsencrypt/live/<staging-host>/fullchain.pem` and `privkey.pem` files. It does **not** obtain certificates, alter DNS, bind sockets or install into `/etc/nginx`. Do **not** create dummy certs in the real Nginx configuration. Set up staging DNS/TLS using your actual DNS/certificate provider, verify it does not collide with any existing `server_name` or `default_server`, and only then use your normal change-control process to install the reviewed vhost. Before reload:

```bash
sudo nginx -t
```

If syntax or host collision validation fails, **do not reload**. Preserve the old config and roll back only the two added staging vhosts. Never overwrite the production `micor.top` vhost or its current certificates.

The GitHub `mcp-staging-tls` CI check tests real Nginx with disposable **self-signed certificates only inside the disposable runner**, two loopback mock backends, correct SNI/Host and `X-Forwarded-Proto`, non-production ports, and denial of public Keycloak admin/master access. It is an acceptance gate for the template, **not** proof that real DNS, production certificates, or an accessible staging host already exist.

## 5. Enable read-only staging OAuth *after* TLS and Keycloak validation

Edit only `app/deploy/mcp-staging/.env`:

```properties
PRP_STAGE_MCP_ENABLED=true
PRP_STAGE_OAUTH_ENABLED=true
```

Confirm `PRP_STAGE_AUTH_ISSUER`, `PRP_STAGE_AUTH_JWKS_URI`, `PRP_STAGE_MCP_RESOURCE` match the externally reachable HTTPS URLs **exactly**, rerun `python3 check_env.py --env-file .env`, then recreate only the staging backend:

```bash
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml up -d --no-deps backend
```

The staging stack **always** sets `MATRIX_PRP_MCP_WRITE_ENABLED=false`; OAuth must be active if MCP is active.

Validate unauthenticated public discovery and 401 authorization challenge **from a separate trusted machine**:

```bash
cd ../mcp-oauth
python3 public_route_preflight.py \
  --resource https://prp-test.micor.top/api/mcp \
  --issuer https://auth-test.micor.top/realms/prp-mcp
```

Then log into the staging PRP test account, approve the test client for **only `prp.tasks.read`**, and issue a 10-minute one-time link code. On your local browser workstation, run `pkce_smoke.py` (see `../mcp-oauth/README.md`) to perform Authorization Code + PKCE sign-in and a read-only MCP round-trip with the external Keycloak issuer.

## 6. Acceptance criteria / rollback

Acceptance requires: staging DB schema isolated; PRP Web login works at `/prp/`; OAuth discovery and 401 challenge match exact public resource; Keycloak signs a real token for `prp-test.micor.top/api/mcp`; owner binds issuer+subject via one-use ticket; `initialize → tools/list → prp_tasks_list` works; unauthorized finance/write are denied; client revocation prevents subsequent calls; production services remain untouched.

Stop only the staging projects (omit `-v`, which would remove their **staging** persistent volumes):

```bash
cd app/deploy/mcp-staging
docker compose --project-name prp-mcp-stage --env-file .env -f compose.yaml down
cd ../mcp-oauth
docker compose --project-name prp-mcp-auth --env-file .env -f compose.yaml down
```

**Never use `docker compose down -v` without deliberately deciding to destroy the staging databases.** Do not merge PR #95 or flip production feature flags until a live OAuth grant and real network MCP client test pass, the release-preservation gate is cleared, and a reviewed deployment plan exists.


### Important: production V24 / legacy staging V24 collision

Production `main` already applied **V24__vocal_song_library_and_assignments.sql**. The initial MCP staging installation applied a *different* `V24__mcp_write_drafts.sql`, followed by legacy MCP V25 and V26. This branch reconciles **new/fresh** lineage as production vocal V24, MCP drafts V25, grants V26, links V27. SQL bodies for the MCP tables are unchanged; their historical SQL header annotations retain the former version numbers and must not be used as migration identities.

**Do not deploy a newly built backend from this lineage against the existing stateful `matrix_prp_mcp_stage` database.** The old Flyway history is incompatible and should fail validation. Never silently call `flyway repair`, use `clean`, rewrite applied migration history, overwrite the stage volume, or point this checkout at production. Preserve stage data and evidence unchanged until a separately reviewed, independently backed-up synthetic-stage cutover has passed real MySQL tests. See `app/docs/technical/mcp-flyway-lineage-reconciliation.md`.

## PR #113: first-party PRP ↔ Keycloak account bootstrap (review-only, default OFF)

The first-party PRP sign-in flow is **separate** from the official ChatGPT OAuth client. It exists so a user can associate a PRP owner with a verified Keycloak `(iss,sub)` without pasting tokens or tickets into ChatGPT. The code has passed disposable Keycloak 26.8 + MySQL 8.4 + Java 21 + Chromium end-to-end tests, **not** active staging/public ChatGPT acceptance.

The isolated staging Compose source now passes through the following *default-off* environment variables:

| Staging `.env` input | Compose/Vue destination | Guard |
| --- | --- | --- |
| `PRP_STAGE_FIRST_PARTY_LINK_ENABLED=false` | `MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED` | Disabled unless explicitly enabled after review |
| `PRP_STAGE_FIRST_PARTY_CLIENT_ID=prp-first-party-link` | `MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_CLIENT_ID` | **Exactly** this separate public Keycloak client ID, never ChatGPT's |
| `PRP_STAGE_FIRST_PARTY_REDIRECT_URI=https://prp-test.micor.top/prp/me/mcp-link/callback` | `MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_REDIRECT_URI` | Must match the selected **staging** public host, exact path |
| `PRP_STAGE_AUTH_ISSUER` | Web **build-time** `VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT` = issuer + `/protocol/openid-connect/auth` | Pins the Keycloak URL the browser is allowed to open |

`prepare_env.py` generates a **disabled** state by default. `check_env.py` rejects activating first-party bootstrap unless *both* stage MCP and stage OAuth are enabled, and it validates that the Client ID/Callback are exact. Existing staging `.env` files that omit all three new keys remain disabled and valid. The web image now requires the explicit non-secret pinned authorization URL at build time; this is an artifact of the reviewed Compose build, not an instruction to install a live vhost.

**Important release dependencies that this wiring does not solve:** the first-party public S256-only Keycloak client must be independently registered and checked on the actual desired Realm; the precise PRP callback, login/grant/identity APIs and static assets must be authorized through the separately reviewed Nginx scope (the current V2 raw-URI guard change deliberately does *not* add them); the external TLS chain and HTTPS forwarding trust must be accepted; first-party and actual ChatGPT signed `sub` must be verified to match; actual ChatGPT login, `private_key_jwt`, token refresh and at-most-20 task query must succeed. Do not use a normal browser `/admin` path to manage Keycloak publicly or copy official client private keys to PRP.

**No release authority is implied:** changes in this section are GitHub source-only. B2 remains NO-GO until independent exact-vhost review, real operator approval, authentic `approved-install.safe.json` and new `fresh-b2-restore.safe.json`, all checks by the original controller, and real public acceptance. No installation/reload/Admin REST writes are authorized by this document.
