# P3.7.1 — trusted evidence intake contract (offline only)

Issue #323 / unified Staging #396. This is an isolated Draft implementation based on the current dev baseline. It reuses the P3.6 projection and P3.5 approval-boundary vocabulary; it does not replace either implementation.

## Scope

- app/deploy/staging_trusted_evidence_intake.py: strict versioned model, allowlists, candidate binding, source-reference validation, freshness checks and cross-record consistency findings.
- app/deploy/staging_trusted_evidence_adapter.py: pure adapter from the existing P3.6 read-smoke projection + redacted receipt + separately supplied identity assertion into the normalized evidence model.
- app/deploy/test_staging_trusted_evidence_intake.py: offline synthetic tests. Existing CI discovers app/deploy/test_*.py in its deployment-gate test step; no workflow edit is needed.

## Evidence classes are not authentication

Every record has an explicit claimed source class:

| Class | Meaning | Intake treatment |
| --- | --- | --- |
| github_metadata_claim | Caller-supplied GitHub run/job metadata | Check run, attempt, workflow path, job inventory and candidate/tree bindings; authenticity remains unestablished |
| artifact_bytes_review_claim | Caller-supplied archive/manifest checksum review | Check artifact/witness/source IDs, expiry, file counts and digest shapes; bytes are not read or verified here |
| operator_receipt_claim | Redacted operator runtime, smoke or recovery report | Check candidate/image/schema/identity/rollback consistency; no host is contacted |
| p36_projection_claim | Existing P3.6 offline read-smoke projection | Bind exact request comment, run ID/attempt, workflow SHA, case inventory and separately supplied identity facts; remains a claim |
| owner_uat_claim | Redacted owner/device business test report | Check case IDs, owner aliases, device classes, cleanup claims and freshness; no device or business system is observed |

The adapter always emits source_authenticity=NOT_ESTABLISHED, readiness=NOT_ESTABLISHED, and false authorization/live flags. VALIDATED_FOR_REVIEW means only that the supplied JSON is structurally complete and internally consistent. It is not trusted, verified, deployable or release-eligible evidence.

## Binding and rejection rules

- Exact repository micor-cjj-spec/matrix-prp, repository ID 1261866723, issue #396, and environment prp-unified-396.
- Candidate binds source commit/tree, schema, Backend/Gateway image IDs, artifact ID/archive digest, and the distinct witness run/attempt/SHA. Witness commit is not silently substituted for the source commit.
- Only the allowlisted CI and unified Staging read-smoke workflow paths are accepted. Candidate CI and artifact-witness CI are separate, explicit run roles; each requires a full job inventory whose jobs bind to the same run, attempt and head. The witness run must match the candidate witness run ID, attempt and SHA, and must not be conflated with candidate CI. Duplicate jobs, stale attempts, incomplete/failed jobs and candidate/tree mismatches remain findings.
- Artifact witness facts bind the artifact ID, witness run/attempt/SHA, original source SHA/tree, archive digest, Backend/Gateway image IDs and expiry. A claimed byte review requires both archive-byte and manifest digests plus a complete file count; these remain caller claims.
- Runtime facts bind exact Backend/Gateway image IDs and schema while separately asserting MySQL unchanged. Production-targeted, MySQL-mutated, unhealthy or rollback-incomplete claims remain explicit findings.
- P3.6 adapter accepts only the fixed U01–U09 / 11-check read-only receipt contract, matches request comment/run/attempt/workflow SHA, and requires all live/deployment/production flags false. It does not accept a browser or business UAT as equivalent.
- Business, device and backup/restore records use redacted aliases and fixed case schemas. Synthetic writes require a cleanup PASS claim; cross-module suites require two owner aliases; restore source and target must be distinct.
- One current record per evidence kind is allowed in a bundle. Duplicate kinds/references, unknown fields, unknown workflows, future observations, stale observations and missing required evidence kinds are rejected or explicitly reported.
- Freshness windows (15 minutes for runtime/read smoke; 24 hours for CI/artifact/business/device/restore) are provisional intake limits, not operational SLAs, retention promises or RPO policy.

## Execution and safety

Offline only. No network transport, GitHub API, signature verification, artifact download, host/SSH/Docker access, SQL, Flyway, browser control, credentials, OAuth/Keycloak/MCP grant, runner dispatch, scheduled workflow, business write, approval, deployment or publication-hold change. No workflow or existing file is modified.

Run locally from repository root: python3 -m unittest discover -s app/deploy -p 'test_staging_trusted_evidence_intake.py' -v

The existing CI deployment-gate-tests step already discovers test_*.py in app/deploy, so the new suite is included without changing CI configuration.

## Deliberately deferred

P3.7.2: independently authenticated GitHub/artifact/runtime/DB/UAT source receipts and before/after runtime observations.
P3.7.3: server-owned CurrentReview bridge, independent reviewer/session proof, atomic freshness and durable decision journal.
P3.7.4: offline combined approval/report simulation and negative replay/staleness/hold tests.

No P3.7.1 output may satisfy P3.5 CurrentReview PASS, change the #396 runtime state, activate the live runner, register an approval tool, or authorize a deployment.
