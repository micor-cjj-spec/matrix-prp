# PRP CI/CD V2 — release-scope advisory (review proposal)

This document describes the proposed **candidate-scoped acceptance** policy. It is not approval to deploy, remove the global hold, relax CI, or bypass production controls.

## Why candidate-scoped is not module-independent deployment

PRP currently packages one `backend.jar` plus the Web build as `release.tar.gz`. The complete selected commit is deployed together. A "UI-only change" means **the diff may need a narrower specialist UAT**, not that only UI binaries are installed or that the backend, database, authorization and recovery checks can be skipped.

## Proposed release sequence

1. A feature is developed on its own branch. PR to `dev` runs the existing full CI, Feature Impact, and an **advisory** release-scope report. The report classifies paths conservatively and proposes candidate-specific evidence. Unknown paths require manual classification.
2. Merge to protected `dev` only after the branch protections and checks are independently configured and reviewed. Review the exact merged tree, not a previous per-PR green result.
3. Use **independent staging**, synthetic identities/data, real browser or contract tests as appropriate. API/auth/MCP changes require negative isolation tests. DB/Flyway changes require backup/recovery rehearsal in an isolated clone before any production approval.
4. Build a reviewed `dev → main` candidate with immutable commit SHA, a complete source and dependency diff, a risk register and signed-off module checks. A separate owner decision is required to merge to `main`.
5. Retain the checked-in global `publication-hold.json` until a **separate, explicitly approved** transition to the replacement policy. Do not infer approval from PR labels/comments, CI success, or ChatGPT discussions about planning.
6. If and only if every independent production gate is satisfied, the protected `production` environment can deploy the **exact release artifact** through the existing restricted SSH and approved controller; never use generic shell or ad-hoc production DB updates.
7. Read back deployed commit, schema and health/smoke evidence from production. Log the run, actor, release ID, artifacts and recovery options. A green workflow with skipped `publish` is **HELD**, not LIVE.

## Candidate-specific specialist evidence

| Changed surface | Extra acceptance evidence | Never skipped |
| --- | --- | --- |
| Docs/test only | CI and review; no application release necessary | Existing change-control policy |
| UI/PWA view or assets | Actual browser, Safari/PWA accessibility and app navigation relevant to the diff | Main CI, approved release and rollback controls |
| Backend domain | Business, data isolation, legacy compatibility and integration tests | Main CI, staging, backups and approval |
| Shared route/client/layout | Cross-module compatibility tests | Main CI, staging and approval |
| Migration / DB schema | Exact Flyway lineage; fresh isolated backup/restore rehearsal and rollback compatibility | DB preservation and restore safeguards |
| OAuth/MCP/permissions | Consent, scopes, revocation, tenant/owner separation and negative tests | Production authorization guard |
| CI/deploy/SSH/controller | Workflow-contract, restricted identity, provenance and failure-mode validation | Existing production environment rules |
| Unknown | Manual path/owner assessment (fail closed) | All existing controls |

**Important:** This is a test/reporting change only. `release-scope.mjs` cannot authorize deploy, determine that a real environment was tested, or establish LIVE status. Its inputs can be modified in a PR and must not be treated as trusted authorization evidence. All actual gates remain enforced elsewhere, and this proposal adds **no** ability to override them.

## Separate next milestones

- Define the trusted evidence bundle: candidate SHA, exact PR diff, required CI run IDs, independent staging evidence, database/authorization impact, approval identity and production controller readback.
- Implement the production-safe candidate gate against trusted GitHub and controller evidence with a standalone contract test, retaining fail-closed behavior and preserving the existing global hold while under review.
- After successful nonproduction rehearsal, obtain a distinct owner authorization to configure protected `dev`, enforce `dev→main`, and replace the exceptional global freeze with auditable per-release approval. These are **not** approved in this PR.

Related issues: #323 (unified CI/CD), #317 (main/dev governance), #326 (untrusted status classification), #260 (Health V2), #262 (UI V2), #316 (CI infrastructure stability).
