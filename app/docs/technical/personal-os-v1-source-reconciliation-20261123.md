# Personal OS V1 — dev source-reconciliation checkpoint (review only)

> **DRAFT · NO SOURCE MERGE · NO HOST/DB/OAUTH CHANGE · NOT A DEPLOYABLE RELEASE CANDIDATE**

This is the frozen *source promotion input map*, not new application code. It prevents accidentally promoting unrelated remote-shell, Health V2 or older governance/CI changes from the stacked Personal OS branch.

## Provenance, 2026-11-22 19:18+ UTC

- Repository: `micor-cjj-spec/matrix-prp`.
- Exact checked `dev`: `5834005c468a5e5178fd65278ad8de83426bb9c6` (unprotected when read).
- Canonical functional Personal OS T-007 Draft [#311](https://github.com/micor-cjj-spec/matrix-prp/pull/311) head: `009b97af4dcab7938cb6e01bd6c95271d35aa7a6`.
- A real git compare `dev...#311` reports **diverged, 137 ahead / 13 behind, 99 changed paths**. This does *not* independently prove a merge conflict; it proves the branch must not be promoted by a blind fast-forward.
- Existing CI-only Personal OS + UI candidate [#342](https://github.com/micor-cjj-spec/matrix-prp/pull/342) at `efc22eddf8fc6e3dd81e2b4413b62a43c35ff751`: complete synthetic [CI 34/34](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45020540340), browser [2/2](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45020540321); **never merge or treat that CI branch as a production artifact**.
- This document's companion `personal-os-v1-source-map-20261123.json` is the **entire 99-path** classification with exact GitHub diff statuses; it is not permission to copy every listed file.

## Differences that must be explicitly handled

| Classification | Paths | Release handling |
| --- | ---: | --- |
| Personal OS-only new sources and unit tests | **40** | Eligible for reviewed exact-blob extraction, subject to complete parent dependencies |
| Shared feature registration, API, Vue and MCP code | **17** | Individually reconcile current `dev` plus feature changes; preserve all existing capabilities and four tabs |
| Health V2 / Flyway V30 dependency | **7** | **Not owned by Personal OS**. Coordinate Health V2 owner; V30 must precede Personal OS V31 with verified matching SQL/policy hashes |
| CI, migration policy, integration/OAuth tooling | **22** | Preserve `dev` workflows, wrapper, release controls; select only independently reviewed Personal OS test deltas |
| Unrelated ChatGPT remote shell feature | **13** | **Explicitly exclude**. Never enable chat-shell or copy its gateway, cert or workflow as part of Personal OS |
| **Total** | **99** | Every changed path has exactly one initial owner/review category |

## Next proposed source-integration operation (not executed here)

1. Base a **fresh, separately authorized functional candidate** on the then-current `dev` SHA, not the test-only #342 branch and not the full ancestor history of #311.
2. Carry reviewed Personal OS-only files via exact Git blob SHA after checking their dependencies. Do not silently use a newer branch revision.
3. Resolve each of the 17 shared path overlays with an explicit current-`dev` preservation diff. In particular reconcile MCP registries/scopes, feature registry, router, apps catalog, AI/chat view, task selection and tests. Do not enable read/write scopes or automatic chat extraction.
4. Have the Health V2 owner confirm V30 migration ordering, actual SQL checksum, and `migration-policy.json` V30/V31 rules; do not introduce another V30 or modify applied Flyway history. Never run Flyway against existing production or stateful V2 staging.
5. Preserve `dev` CI, publication hold, deployment workflow, branch protection discussions and all independent feature work. Reconcile tests without deleting existing checks.
6. Run **new exact-head CI** for the resulting candidate, including backend, Vue/PWA, disposable MySQL migration, owner-isolation, mock provider consent, mobile Chromium/WebKit, old MCP/Health regressions. Fail closed on any new SHA without matching completed evidence.
7. Before any persistent preview, obtain separately approved independent VM/DNS/TLS, fresh empty DB and isolated credentials; actual iPhone Safari/PWA, data privacy and provider permission acceptance remain open. See [T-009 #301](https://github.com/micor-cjj-spec/matrix-prp/issues/301) and [T-007 #188](https://github.com/micor-cjj-spec/matrix-prp/issues/188).

## Security and governance

This PR contains **only this Markdown and its inert JSON inventory**. It does not modify Java/Vue runtime, tests, migrations, `dev`, `main`, OAuth, MCP grants, production or staging. `app/deploy/publication-hold.json` must remain. No production deployment, source merge, branch ruleset change, real user data transfer or ChatGPT-shell activation is authorized by this source map.

If `dev` or #311 changes, recompare exact SHAs and regenerate a *new reviewed inventory*. Never imply a green test on another SHA certifies it.
