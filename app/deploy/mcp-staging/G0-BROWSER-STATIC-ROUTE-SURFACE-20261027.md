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
