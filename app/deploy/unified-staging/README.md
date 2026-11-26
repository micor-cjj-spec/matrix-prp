# Unified PRP Staging — S1 review-only deployable shape

**NO-GO / UNINSTALLED / NOT AN INSTALLER.** [Issue #396](https://github.com/micor-cjj-spec/matrix-prp/issues/396) owns the full environment decision. This directory is an **offline candidate** reviewed against existing PRP Dockerfiles; GitHub CI may parse it and may start **only disposable GitHub-hosted runner containers** via the separately guarded `smoke_disposable.sh`; it must never create a persistent server stage, alter host routing, or claim a live endpoint. No authority to modify production, :11000, legacy :18081, V2 :18082, NewDB :18083, Keycloak, DNS, Nginx or OAuth clients.

## Why one shared full-app stage but still isolated test sandboxes

- Full Web/PWA, API and private MySQL in one dedicated Compose project; reuse the existing Java 21 and Vue build sources from `app/deploy/mcp-staging/Dockerfile.backend` and `Dockerfile.web`, not production artifacts.
- Three services are behind `profiles: [unified-review]`. No default stack exists and **there is no install workflow**.
- Only gateway publishes an explicit, unapproved-until-inspected `127.0.0.1:${PRP_UNIFIED_LOOPBACK_PORT}`. MySQL/backend have no host port publishing.
- Java and MySQL use an internal network. The gateway additionally joins a dedicated bridge for its host-loopback listener. The dedicated volumes are `unified_mysql`, `unified_video`, `unified_vocal`, private DB `matrix_prp_unified_stage` and user `prp_unified`. Do not import existing personal data, reuse V2/test databases, or mount any old volume.
- Baseline MCP/OAuth, first-party link, MCP writes and Spring AI integrations are hard-coded OFF. Dedicated Nginx review template returns 404 for `/api/mcp*` and `/.well-known/*`; only ordinary PRP Web/API synthetic-data flows are in scope. External provider and real ChatGPT UAT need separate security approval.
- For the existing Web Dockerfile, an exact **stage-only** authorization URL is a build-time argument. Its presence does **not** activate an OAuth service or grant; the gateway denies related MCP routes, and no Keycloak instance is provisioned by this candidate.
- `.dockerignore` excludes nested `.env` and private key files; local `.env` must never be committed, logged, or placed in a Docker build context.

## Static-only validation, not an installation

The source `.env.example` consists of deliberately invalid placeholders. After a separately authorized target selection, an operator can prepare a **fresh local-only** .env with a new dedicated HTTPS hostname, separate auth issuer placeholder, exclusive port, and **four unique 64-digit random lowercase hex secrets**, then locally run:

```sh
python3 app/deploy/unified-staging/check_env.py --env-file /private/path/staging.env
docker compose --project-name prp-unified-stage-review \
  --env-file /private/path/staging.env \
  --profile unified-review \
  -f app/deploy/unified-staging/compose.review.yaml config --quiet
```

These commands only validate config and **do not install**. The Python validator intentionally always reports `deployment_permitted=false`; a valid DNS syntax, port number or Compose YAML cannot prove that a host, ingress, real TLS, MySQL volume, migration or capacity is safe.

### Mandatory independent gates before a live install

1. S0 host read-only inventory and distinct ownership of production/18081/18082/18083, CPU/available memory/disk, legacy volumes/ports, ingress/Host/SNI and backup responsibilities.
2. Owner/operator approval of **specific host**, stage-only resource envelope, unused port, DNS/TLS config and network/volume boundary. **Do not redirect `prp-test.micor.top` or `auth-test.micor.top`; these belong to existing V2 history.**
3. Independently reviewed source SHA, immutable backend and Web digests, Flyway checksums/order (Health V30, Personal OS V31 as applicable), exact branch integration and plan to initialize a fresh stage-only schema.
4. Separate review/installation controls and rollback for new stage-only resources. No remote-host `docker compose up/down`, Nginx reload, DNS changes or persistent database operations in this PR or its CI. Only the explicitly guarded, disposable GitHub PR runner may bring up its own isolated synthetic containers and clean them up.
5. After actual installation approval, authenticated synthetic-user/UAT evidence: four tabs and all original app entry points, iPhone Safari/PWA, health/learning/Personal OS, server-side owner isolation, stage rollback. MCP/OAuth/ChatGPT E2E remains separately gated.
6. Trusted actual runtime collection of SHA, digest, schema, live HTTPS, isolation and UAT outcomes. Never treat a green CI as `STAGING_VERIFIED` or `PRODUCTION_READY`.

## Scope of this Draft

Only `app/deploy/unified-staging` and disposable CI contracts are added. The new runtime CI boots synthetic MySQL/Java/Web on a throwaway GitHub-hosted PR runner, checks health, `/prp/`, denied MCP and wrong-Host routes, and the Flyway version, then tears down **only its own** Compose project and volumes. This remains **CI evidence only**, not an installed persistent staging system. No production scripts, existing staging Compose, release gates, `main`/`dev`, `publication-hold.json`, OAuth clients, secrets or host resources are changed.
