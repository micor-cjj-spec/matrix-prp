# CI/CD V2 candidate evidence inventory (offline)

Related #323, #396 and the consolidated #412. This is an offline inventory format, not a trusted collector, controller, approval mechanism or release lock. It has no network or production access.

## Input

JSON schema version 1, with exact fields:

- candidate: repository (fixed matrix-prp), commit (actual tested tree's full SHA, not a mutable ref), artifact_digest (sha256: plus 64 lowercase hex, or null until built), schema (expected numeric Flyway version, or null).
- hold: state active/clear/unknown, commit, sanitized opaque ref. A mismatched SHA becomes unknown, never clear.
- evidence: optional gate records. Omission means pending/missing; skipped and failed are never successful. Each record has source, environment, commit, status (pass/fail/pending/skipped), ref (sanitized opaque receipt ID). Unknown fields are rejected.
- CI additionally supplies run_id, run_attempt, tested_commit and all_jobs_success. A PR head is not automatically the tested merge SHA. Never reuse CI on another tree.
- Risk additionally supplies risk (one of the existing five release-scope classifications). UNCLASSIFIED requires review.
- Artifact, staging, migration, backup_restore, approval, publish and production_smoke additionally carry artifact_digest and schema; mismatches cannot count. Approval records are declarations only, not authorization.

| Gate | Source | Environment |
| --- | --- | --- |
| ci | github_actions | review |
| risk | risk_report | review |
| artifact | build_manifest | review |
| staging | staging_receipt | staging |
| migration | migration_receipt | staging |
| backup_restore | restore_receipt | staging |
| approval | owner_decision | production |
| publish | controller_receipt | production |
| production_smoke | smoke_receipt | production |

Use #396's future reviewed test-env-status and real staging UAT evidence to populate staging/migration/restore receipts. A CI-only Compose run is not a persistent environment receipt. Never use production data for testing. These receipt types are proposed adapters, not yet implemented or independently verified.

## Run locally on synthetic input

    python3 app/scripts/release_evidence.py --input candidate.json --json release-evidence.json --markdown release-evidence.md

Outputs include all gates, owners, missing or stale evidence, blockers, candidate bindings, asserted run/attempt and artifact/schema provenance, hold reference, and one logical state. Opaque references must not include URLs or secrets. The inventory is a separate, more complete schema than the six-check legacy projection; it does not embed a second potentially conflicting state. Use the inventory to diagnose a candidate, not to display authoritative production state. Even all-pass caller assertions return deployment_authorized=false, release_eligible=false, live_verified=false. Pre-publish completion and publish/smoke are distinct; a checked-in hold cannot be waived by any receipt. For docs-only changes the separate risk advisory may recommend no application release; this inventory never grants an exemption for a candidate actually being published.

Only a separately reviewed trusted collector may later retrieve real GitHub run/attempt/checkout and controller evidence, validate identities and freshness, and populate the inventory. Actual production eligibility and LIVE remain outside this module. No changes to Deploy PRP, publication-hold.json, health workflows, or environments.

## Unified Staging S6 review adapter (#396 / #411)

The upstream #411 S6 validator at review head 1b07b3d7d3aeeef5ebd70242ed4fa6787097ed3a emits a six-field sanitized JSON summary. Its v1 contract explicitly supports only blocked/repository-review evidence. The candidate inventory optionally consumes that summary via `--staging-review s6-review.json`, after an operator runs the independently reviewed upstream validator in its own checkout. This is an offline input; no download, execution of upstream code, server action or automatic trust is added. Do not pass raw host or deployment information. The consumer accepts only the blocked/not_established summary, keeps both authorizations false, and preserves archive clock expiry as an assertion. Any staging gate remains pending, even if another caller asserted successful staging; the contradictory review-only evidence is a blocker. The current blocked snapshot is not a runtime receipt and cannot supply artifact digest, Flyway schema, actual UAT or backup/restore proof. A later verified S6 receipt format must be separately agreed with #396 before it can be adapted.

Example (synthetic input, using separately saved #411 validator summary):

    python3 app/scripts/release_evidence.py --input candidate.json --staging-review s6-review.json --json report.json --markdown report.md

This avoids copying #411's validator or modifying its branch. The existing release-evidence test entry covers the consumer contract.
