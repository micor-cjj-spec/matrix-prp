# PRP MCP: hosted OAuth on a single 4C8G production server

Status: REVIEW ONLY — **not authorized for release**.

Latest operator-supplied read-only snapshot on 2026-10-21, after stopping the
Matrix microservices and their supporting containers:
- Host MemAvailable: **6091 MiB**; SwapFree: **2017 MiB**; root disk free: **39.9 GiB**.
- PRP remains active/running; process RSS **311.2 MiB** (systemd MemoryCurrent about 298 MiB).
- Only `matrix-mysql` was listed as a running Docker container; Nginx remains active.
- A prior process scan still showed the OpenClaw Gateway user service (about 389 MiB,
  loopback port 18789), so this host is not literally running PRP alone.

This latest sample clears the script's preliminary 1536 MiB available-memory and
10 GiB free-disk review thresholds. The earlier 1289.7 MiB sample was taken while
the Matrix stack was running and describes a different host workload. This is still
**one snapshot, not a peak-load test or deployment approval**. The checker always
returns `safe_to_deploy: false` by design and requires separate manual review.

Do not deploy the production-facing OAuth/MCP feature. A local-only isolated staging
stack with separate credentials and databases may be evaluated after compose/env
preflight and an explicit operator decision. Do not configure public DNS/TLS or start
the OAuth stack merely because the capacity threshold now passes.

## Resource-efficient topology

ChatGPT/compatible client authenticates through a hosted OAuth provider.
The signed access token goes to the already existing PRP Java process's
/api/mcp endpoint. PRP validates the HTTPS JWKS, issuer, audience, signed
client, user association and owner-approved scope on each request.
Existing MySQL stores only V24–V26 draft/grant/identity tables. This
avoids **local** Keycloak/PostgreSQL resource consumption but requires
a trustworthy provider, operational reviews and measured Java capacity.

## Provider decision

1. **Hosted Auth0 is a candidate, not yet approved.** Its Resource
   Parameter Compatibility Profile must be enabled so the OAuth
   resource parameter selects the intended API audience. Configure
   the API identifier to equal the canonical public PRP MCP URL.
   Do not rely on Auth0's legacy audience parameter alone. Auth0's
   OIDC issuer commonly has a terminal slash; preserve it exactly.
   Signed tokens sometimes contain an additional /userinfo audience.
   PRP currently requires the exact MCP resource as one of the signed
   audiences, plus issuer, verified subject, client identity and
   PRP-side consent. Extra audiences must be explicitly risk-reviewed.
   Vendor billing, DCR support and terms are not yet confirmed.
2. **Do not assume another hosted IdP is interchangeable.** Current
   ZITADEL DCR docs state RFC 8707 resource may be ignored for
   audience narrowing. An issuer is not PRP-compatible until an
   actual PKCE token passes the configured MCP audience verification.
3. **Self-hosted Keycloak reference** passed full disposable CI PKCE,
   owner-link and MCP read/revocation tests; that does NOT justify
   permanently deploying Keycloak+PostgreSQL onto the current 4C8G.
4. **Building an authorization server inside PRP is deferred.**
   Implementing DCR/CIMD, user consent, PKCE, signing, rotation,
   refresh/revoke and auditing is a separate security-sensitive
   project, not a trivial RAM optimization.

## No-credential hosted issuer discovery gate

Run on a trusted machine or ephemeral CI runner:

    python3 app/deploy/mcp-oauth/hosted_issuer_gate.py \
      --issuer 'https://YOUR_TENANT.us.auth0.com/' \
      --resource 'https://micor.top/api/mcp' \
      --client-mode dcr

Use --client-mode cimd ONLY if discovery supports CIMD and an OpenAI-
compatible token authentication method. For a reviewed pre-registered
OAuth client use --client-mode provided --registered-client-id CLIENT_ID.
This tool does not register, log in, fetch tokens or change settings.
Passing discovery means **metadata_only, never production ready**.
CIMD, DCR and pre-registered OAuth client IDs must match the actual
ChatGPT connection's registration method and callbacks.

## Read-only PRP server memory check (Codex/operator only)

On the **existing 4C8G production server**, in the separate read-only
checkout of this review branch, run:

    python3 app/deploy/mcp-oauth/read_only_capacity.py

The command requires no sudo on ordinary systemd/procfs deployments.
It reads only: allowlisted aggregate /proc/meminfo, /proc/loadavg,
the root filesystem's free bytes, selected 'systemctl show
matrix-prp.service' fields, and /proc/<MainPID>/status values limited
to RSS, peak RSS and thread count. It never reads process command
lines, environment, secrets, Java heap dump, application data/logs,
database rows, external OAuth providers or production config. It
does NOT start, reload or interrupt any service.

The output intentionally hides PID, server identity and paths, and
always contains 'safe_to_deploy: false'. Treat the initial 1536 MiB
MemAvailable and 10 GiB free-disk values as conservative **review
thresholds**, not sizing guarantees. An operator's earlier observation
of ~1.3 GB available RAM would trigger a low-headroom warning; only
a fresh measured sample can confirm current pressure.

Collect snapshots for the intended service topology at normal and representative
peak times, preferably on different days. If a sample under that same topology is
pressured, do not add an OAuth service to this host. A snapshot taken before the
Matrix services were stopped should be retained as historical context, not treated
as the current post-stop baseline. This check does not measure GC pauses,
database memory, network latency, heap usage or real peak workloads; production
deployment still needs independent operator approval and the preexisting
release/data-preservation gates.

Avoid copying outputs containing user- or vendor-specific diagnostic
extensions into public issue comments. The intended script output
contains only allowlisted numeric capacities and generic unit state.


## ChatGPT client entitlement and device gate (review-only)

As reviewed on 2026-10-21, **do not equate a passing MCP/OAuth CI suite with
the ability to attach this server to the operator's current ChatGPT account**.
Check the live official plan/workspace entitlement before spending on hosted
OAuth, adding public DNS, or enabling production MCP. Current OpenAI help
documents custom remote MCP server connections for Business and Enterprise/Edu
workspaces (admins/authorized roles); Pro has limited read/fetch support.
They do **not** affirm arbitrary Plus user-created remote MCP connections.
Custom MCP setup is web-only in the documented flow; an iOS ChatGPT session
is not a substitute for the required web-side creation test.

Reference: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

**Blocking acceptance evidence:**
- On the *intended* ChatGPT plan/workspace and a supported web interface,
  show that **Add custom MCP server** is permitted for the account/role.
  A separately connected GitHub plugin or a successful API-level MCP test
  does not demonstrate this entitlement.
- Confirm whether this account permits the intended read-only tools, and
  separately whether any future write tools are permitted. Never infer
  write entitlement from server capability.
- Verify that the actual ChatGPT client supports the chosen CIMD/DCR or
  pre-registered OAuth client mode and its exact redirect URIs.
- Authenticate with only disposable staging credentials, obtain real
  JWT evidence, and test PRP-side link, tasks.read, revocation and
  refresh-token behavior before any production canary.
- If account eligibility cannot be verified, leave all production MCP and
  write feature flags **OFF**. Continue isolated GitHub CI only; do not
  provision an OAuth tenant on speculation or suggest that an account
  upgrade is required for the PRP application's internal AI features.

The existing `prp-readonly-inspect.yml` / forced `prp-inspect` command
reports only allowlisted deployment/service metadata; it **does not**
run `read_only_capacity.py` or collect JVM/host resource headroom.
This new capacity script is source in the draft PR, not an installed
production command. A real resource snapshot requires a separately
authorized **read-only** operator execution in a separate checkout.
Do not broaden the forced-SSH command, install software, dispatch a
production deployment, or treat the earlier 1.3 GiB observation as
a current measurement.

## Required independent live gates

- Provider admin must enable and verify RFC 8707 resource propagation
  in BOTH authorization and token requests. Check PKCE S256, real
  client registration, scope/consent policy, refresh/offline_access and
  token endpoint authentication method.
- Obtain a genuine test-user access token after Authorization Code +
  PKCE. Verify JWKS RSA signature, EXACT configured issuer and signed
  subject, audience containing canonical MCP URL, client_id/azp,
  granted task scope, expiration and rejection of wrong resource.
- Authenticate to PRP with a test account, password reauthenticate,
  authorize a known client, issue one-use link code, and test the
  bearer-only link endpoint, replay rejection, MCP read and immediate
  PRP-side grant revocation.
- Perform read-only capacity review on existing PRP heap/RSS, RAM,
  CPU, connections and disk at normal and peak loads. "No extra
  container" is not proof that existing JVM has adequate headroom.
- Production database currently V23: verify full backup restore,
  strictly additive migrations V24–V26 and all SSH/SFTP release
  controller and data-preservation gates. Never baseline or clean
  an existing populated database without approved recovery.
- Review production TLS, Host, Origin, rate limits, error logs
  (no secrets), provider outage behavior, JWKS rotation, credential
  lifecycle and revocation. Only then separately authorize read-only
  canary deployment with MCP write flag still OFF.

This document does NOT authorize any live OAuth tenant registration,
production migration, DNS/certificate changes, merge or deployment.

## References

RFC 8707: https://www.rfc-editor.org/rfc/rfc8707

OpenAI MCP OAuth: https://developers.openai.com/plugins/build/auth

Auth0 resource compatibility:
https://support.auth0.com/center/s/article/mcp-audience-error-with-auth0

ZITADEL DCR resource limitations:
https://zitadel.com/docs/guides/integrate/dynamic-client-registration

OpenAI MCP entitlement / refresh requirements:
https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt
