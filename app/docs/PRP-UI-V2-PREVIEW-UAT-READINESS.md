# UI V2 Preview / Physical-iPhone UAT — operator handoff (NO DEPLOY)

**State: BLOCKED / NO-GO.** This is a one-file review artifact for [UI V2 release gate #262](https://github.com/micor-cjj-spec/matrix-prp/issues/262). It creates **no** host, URL, database, credential, GitHub environment, rule, service or production release. Do not mistake a synthetic CI run or a filled checklist for an actual installation or authorization.

## 1. Which code is under review?

- **UI-only source**: Draft [#366](https://github.com/micor-cjj-spec/matrix-prp/pull/366), exact source HEAD `f68d4ff1b91090b83046a21e1de02dfb8a8bb52c`. This preserves 首页/应用/聊天/我的 and the existing application catalog, health/learning/chat functions, permissions, API routes and backend.
- **Synthetic CI compatibility only**: Draft [#367](https://github.com/micor-cjj-spec/matrix-prp/pull/367), exact HEAD `ce8133816d76eb3f6e0b1a756f04f7bcc2395c7b`. It adds **one existing Health timezone test-fixture change**, not an application feature. Full CI **34/34 PASS**, UI/source browser **5/5 PASS** for this SHA. **NEVER MERGE #367 AS PRODUCT SOURCE.**
- #366 exact-head UI/source/browser **5/5 PASS**; its full CI **33/34**, because the Health date fixture is absent. The final independent source/integration candidate must be retested at its **own** exact SHA after properly reviewed fixes. Never inherit a PASS badge from another SHA.
- At this checkpoint: `main=2d8afddc4cfd39e5801133a664ed52cae342651e`, `dev=5834005c468a5e5178fd65278ad8de83426bb9c6`. They have diverged. Neither this document nor PR #366 is an authorization to merge.
- Existing [UI V2 implementation and detailed UAT cases](./PRP-UI-V2-QUIET-INTELLIGENCE.md) live in the UI source branch, **not** necessarily in the unmerged dev/main trees. See its IOS-01..04, APP-01 and role/health/chat tests; do not replace those tests with this handoff.

## 2. Preview prerequisite — request actual evidence, not assumptions

An operator and owner must approve a **dedicated** preview environment **before** any host change. First establish and record the following **redacted** facts; mark any unknown item `BLOCKED`:

| Requirement | Required evidence (do not post secrets) | Status before observation |
| --- | --- | --- |
| Independent runtime | Actual approved VM/host and owner; isolation from production and existing MCP V2 staging | BLOCKED |
| Unique HTTPS origin | DNS name, TLS hostname/certificate verification, ingress restrictions; distinct from `micor.top`, `prp-test.micor.top`, `auth-test.micor.top`, `auth.micor.top` | BLOCKED |
| Port and volume ownership | Read-only inventory of listeners, Compose projects, Nginx vhosts and mounted volumes; collision-free stage-only port and fresh volumes | BLOCKED |
| Dedicated data | **Fresh synthetic** PRP accounts and disposable DB; never use `matrix_prp`, existing MCP staging DB, live health records, production exports/backups or production credentials | BLOCKED |
| Authorization behavior | Independent review of test login/role provider, issuer and stage-only consent; no live OAuth/Keycloak changes, production MCP tokens or real ChatGPT writes | BLOCKED |
| Reproducible artifact | Exact UI source / integration SHA, built Web `/prp/` base, backend SHA if applicable, artifact digest and rollback/stop plan | BLOCKED |
| Deployment approval | Explicit approval for **this specific test environment** after inventory; distinct from production release authorization | BLOCKED |

**Known occupied/reserved service references, not an inventory:** production backend `127.0.0.1:11000`; historical separate MCP staging gateways `127.0.0.1:18081`, `127.0.0.1:18082`, `127.0.0.1:18083`. These may have changed. Do **not** attach UI preview to them, replace their vhosts, reuse their DB/schema, or assume they are free. [Existing MCP staging README](../deploy/mcp-staging/README.md) is a template for a **different** workstream, not proof an isolated UI preview currently exists.

No host access is assumed here. No actual preview URL is known or claimed.

## 3. Safe preflight sequence (only after authorized host inventory)

1. Freeze the intended **UI-only candidate** and separately approved dependent fixture fix; inspect changed files against latest dev/main to avoid dragging in other feature branches or missing main-only security commits. Keep original UI/source PR and CI-only preview PR distinct.
2. Reproduce the Web build against the exact candidate in a **separate workspace**: `npm ci --prefix app/web`, then `VITE_APP_BASE=/prp/ npm run build --prefix app/web`; validate the `/prp/` base and expected callback bindings. Do not execute against the production checkout.
3. Confirm a genuinely isolated preview backend, disposable DB with migration lineage, stage identity/role provider, HTTPS Host/SNI restrictions, no production secrets or production mounts; do not perform any schema clean/repair/baseline or modify existing V2 staging.
4. Deploy **only to the explicitly approved preview** using an operator-reviewed plan, record actual runtime source SHA and image digest, assert production + MCP staging remain untouched, and preserve an independently operable stop/rollback for this preview.
5. Only after the operator verifies the live URL, stage health, source SHA, synthetic accounts and safe write-denial defaults may G1/G2 begin. No green GitHub CI substitutes for this runtime proof.

## 4. G1 / G2 human acceptance (actual checks, not mock PASS)

For each case, record `PASS | FAIL | BLOCKED`, environment, device, iOS/Safari version, exact deployed SHA, tester, UTC timestamp and **redacted** evidence reference. If the preview is absent, all are **BLOCKED**.

| Case | Test | PASS condition |
| --- | --- | --- |
| G1-01 | Physical iPhone Safari: 首页 → 应用 → 聊天 → 我的; module → 应用, portrait/landscape | All original routes and bottom tabs remain usable |
| G1-02 | Native keyboard focus, multiline send and chat scroll; dismiss keyboard | No obscured composer; bottom tabs hide only for keyboard and restore |
| G1-03 | Real 200% pinch/pan, increased system text size, long lists, safe area | Zoom works; pinch alone never hides tabs or clips primary controls |
| G1-04 | Add-to-Home-Screen standalone PWA and Safari tab mode, background/resume | Navigation, auth and layout recover without blank screen |
| G2-01 | Ordinary vs admin **synthetic** accounts; switch users | Admin controls server-enforced, no cross-account data |
| G2-02 | Apps search/filter/favorites/reload; learning/video/practice routes | No removed module; catalog/favorite behavior consistent |
| G2-03 | Test-only task mutations and refresh/timeouts | No duplicate writes or false success |
| G2-04 | Six health tabs, synthetic meal/activity/body/goal CRUD and readback | Correct isolated records only; no production personal health data |
| G2-05 | Chat history, streaming, consent/deny/timeout, return from keyboard | No writes before approval; denial stays denied |
| G2-06 | Server audit of rejected requests; stage rollback rehearsal | Denial on server, no secrets in evidence, stage can stop independently |

If either original navigation, access isolation, explicit AI consent, production isolation, or rollback fails: mark **NO-GO**, stop stage-only testing, capture sanitized evidence and escalate through #262. No auto-promotion.

## 5. Evidence handoff / production release decision

Use one row per G1/G2 case:

```text
case_id | PASS/FAIL/BLOCKED | source_sha | stage_host_alias | device_os | tested_utc | evidence_link | defect_id
```

The stage URL and account identity must be sanitized before posting in a **public** repository. Never publish passwords, tokens, personal data, SSH/Nginx config with secrets or screenshots containing them. A passing stage is only **test acceptance**, not automatic permission to merge, change branch protections, remove the publication hold, or deploy.

**Production remains NO-GO** until: (1) G1/G2 evidence passes; (2) protected dev + independently verified same-repository dev→main gate and all required exact-merge-head CI pass; (3) a review-approved release artifact, migration/backup/restore/rollback and production environment policy pass; (4) the owner **separately approves** the exact main commit's production publication. Keep `app/deploy/publication-hold.json` intact.

See [release gate #262](https://github.com/micor-cjj-spec/matrix-prp/issues/262), [production governance draft #317](https://github.com/micor-cjj-spec/matrix-prp/pull/317) and [dev→main source gate draft #306](https://github.com/micor-cjj-spec/matrix-prp/pull/306).