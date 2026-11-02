# G0 review — first-party browser exact-route and static asset surface (2026-10-27)

> **SOURCE/CI CANDIDATE ONLY; NOT AN AUTHORIZATION OR INSTALL.**
> Existing live V2 is still `127.0.0.1:18082`, with older frontend/backend;
> NewDB `127.0.0.1:18083` is a separate, unpublished, OAuth-OFF lab.
> Preserve the original six-file Nginx lineage, B2 NO-GO and PR #113 Draft.

## Independently observed route gap

Real isolated Keycloak + Chromium + Vue + Java + MySQL PKCE/identity-link
tests previously passed with the **broad disposable Nginx test vhost**,
not with the narrow public first-party review candidate.

The first audit replay [40519941568](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40519941568)
**FAILED** after the legitimate Keycloak login, PRP callback and request
checks, reporting one PRP-origin unreviewed `SPA_ASSETS` request.
Diagnostic rerun [40520655085](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40520655085)
**FAILED as intended**, narrowing its safe diagnostic category to
`SPA_ASSETS_FLAT_MULTIDOT_JS` (count 1). These are genuine evidence of
an overly restrictive static asset **filename** rule, not a failed
OAuth token, scope or backend binding.

The source review also found `app/web/index.html` references
`%BASE_URL%favicon.svg`, `%BASE_URL%icon.svg`,
`%BASE_URL%manifest.webmanifest`; `app/web/src/main.ts`
registers `%BASE_URL%sw.js` on secure startup. The Chromium E2E blocks
service workers deliberately, so the absence of `sw.js` in its observed
request list must not be mistaken for proof the deployed PWA does not
need that file.

## Minimal *uninstalled* route-plan delta

`approval_routes_pending.py` now includes exactly **17 explicit
method-scoped paths plus one static asset filename regex**, all
loopback-proxied to **V2 `127.0.0.1:18082`**. Compared to the preceding
13-path task-link candidate, the **only four added exact paths** are:

- `GET /prp/favicon.svg`
- `GET /prp/icon.svg`
- `GET /prp/manifest.webmanifest`
- `GET /prp/sw.js`

The asset regex still permits **only one URL segment** under
`/prp/assets/`, named from nonempty ASCII alphanumeric, hyphen or
underscore components separated by **single periods**, and allowed
`js/css/woff2/woff/ttf/svg/png/webp/ico` extensions. It rejects
`..`, nested paths, `%2f` aliases and other file types; raw URI and
Host/SNI/Authority enforcement remain separate mandatory blockers.
Existing general `render_approval_routes` is **unchanged** and must
not be used for task-read-only OAuth.

**No wildcard `/prp/**` or `/api/**`, no new business read or MCP
write endpoint.** These 17 paths are proposed for independent
Nginx/browser-route review only, not an observed active configuration.
The original G0/B2 receipt and route digest/controller approvals
cannot be silently reused after changing this route candidate.

## Isolated real Nginx canonical raw-URI acceptance (2026-10-27)

The initial actual Nginx HTTP matrix
[40524997179](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40524997179)
found a **real normalization bypass** in the uninstalled first-party
candidate: 14 legitimate canonical browser/API requests were forwarded
to a private mock backend, but at least one percent-encoded raw-URI
alias also reached that backend. Nginx `location =` compares its
normalized route; Python path allowlisting alone was insufficient.

The source-only `render_readonly_link_routes()` candidate now adds
**18** explicit original `$request_uri` checks (17 exact method/path
entries and the asset-name regex). These checks pin the **raw URI path**
while preserving optional `?code`, `?state`, `?iss` and other
query parameters essential to OAuth callback navigation. The old
`render_approval_routes()` TLS review function is not broadened or
changed by this patch.

[40525308297](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40525308297)
**SUCCESS**, as confirmed in its actual job logs on a disposable Ubuntu
GitHub runner. Real isolated Nginx with a synthetic loopback
`127.0.0.1:18082` HTTP backend passed `nginx -t` and:
- **14 canonical** method/path probes forwarded correctly, including
  OAuth callback containing query parameters, both first-party API
  methods, static assets and the expected proxied Host/HTTPS headers.
- **14 negative** probes denied: encoded callback/API aliases, nested
  or malformed asset paths, wrong method, wrong Host, wrong Origin,
  unrelated tasks/finance API and mistaken `/prp/api/mcp`.
- No real PRP, Keycloak, PostgreSQL, MySQL, external TLS, production
  vhosts or user tokens were accessed, installed, reloaded or changed.

A later added Python assertion had a **test-file syntax defect** on
[40525436993](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40525436993),
without a demonstrated Nginx routing regression. The test file was
restored from the last good baseline and a narrower raw-URI assertion
was added. Treat the latest full CI status separately; do not infer
that it passed from the earlier Nginx job.

**Still unverified before any install:** exact original six-file
Nginx/vhost graph, real public Host/SNI/TLS, HTTP/2, IPv6,
browser-origin mapping, old active V2 behavior, the required original
G0/B2 independent authorizations and genuine OAuth/ChatGPT task reads.
This note creates no release authorization and does not target
NewDB at `18083`.

## Current test coverage and missing acceptance

- Python negative contract checks allow exact GET resources and Vite
  dotted file names but reject `..`, nested paths, encoded aliases,
  wrong HTTP methods, unapproved API families and broad draft/write routes.
- Chromium request auditing collects only **method and path on the
  disposable PRP origin**, not OIDC query, code, state, JWT, cookies,
  browser bodies, Keycloak tokens, or user business data. It fails on
  unreviewed requests using only a sanitized path **class**, never the
  URL or filename.
- Source contract checks the four precise build-root files against
  the HTML and service-worker references even though CI Chromium
  intentionally suppresses SW registration.
- **Final fresh Chromium rerun must pass** after the candidate delta;
  do not claim it has passed merely because the previous backend
  PKCE E2E was green.
- Even that rerun would not verify a *real installed public* Nginx
  route set, headers, redirects, nginx normalized request_uri, HTTP/2,
  IPv6, production-grade TLS trust, Safari, source image on current
  V2, Keycloak static client registration, genuine ChatGPT
  private_key_jwt/refresh or owner data.

**Disposition: G0/B2 NO-GO; deployment_permitted=false; no live
ChatGPT `prp_tasks_list`.** The reviewer must separately approve
any updated browser-route package, original active baseline and
valid signed release transaction. Never repurpose this review-only
candidate as a hot Nginx include.
