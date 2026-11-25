# Build reuse coverage and isolated output rehearsal (#323)

Baseline: dev 76aa550b4b6ab3124846d384ce19aa445071aa8c; main dc6fc41824e28c49610fba6d9858629ab0b8a34a; #412 reviewed head 11f736784ef0a094f1141582dbefe9d5f33e4f40 full CI run 45541271154 (34/34). Compare CI and existing Deploy PRP, not a proposed replacement.

| Existing Deploy PRP build requirement | CI evidence | Decision |
| --- | --- | --- |
| Java 21 Maven package, tests | backend-tests Java 21 Maven test | Test phase overlaps; final executable JAR is not produced by this CI command. Keep tests; rehearsal packages after tests without rerunning the unit tests. |
| Node 22 npm ci, production Web build | web-build includes default and /prp/ builds, exact production authorization endpoint and both verify scripts | Rehearse retaining ONLY final /prp/ dist; no deletion of default build. |
| MySQL 8.4 seven integration classes | video-db-integration includes all seven plus FinanceImportDatabaseIT, VocalLibraryDatabaseIT, McpDatabaseIT, McpClientGrantDatabaseIT, McpIdentityLinkDatabaseIT | Test class coverage overlaps, not yet proof of packaging/runtime equivalence. Keep both workflows unchanged for production. |
| Immutable migrations, text encoding | db-migration-integration and web-build | Keep both checks and fresh/legacy migration suite. |
| Python deploy preservation unittest | deployment-gate-tests | Existing deployment discovery/options and dependency environment differ; review separately, no removal. |
| package-release.py, migration policy, release.json | Not performed by ordinary backend/web CI | Keep existing packager and policy checks. No release archive built by this rehearsal. |
| Main freshness, protected environment, SSH/controller, backup, migration, smoke | Not proven by CI | Never substitute CI for production gates. |

Observed one exact-head CI attempt: backend test step 73s; web production-path build step 10s; business integration step 54s. These are PR CI step durations, not measured production savings. CI jobs run in parallel and transfer/packaging overhead matters. Do not add these as a promised wall-clock saving.

## Isolated #412 experiment

Only same-repository PR #412 runs extra steps, after successful original backend tests and final production-configured Web build. The backend performs an additional Maven package with skipTests AFTER the existing test step; it is not skipping the required backend tests. Both jobs stage just the fixed executable jar or final dist, plus ci-output.json containing actual tested Git checkout SHA, source tree, workflow run/attempt, job, scope, per-file SHA256 and sizes. Two separately named short-retention GitHub artifacts (prp-ci-rehearsal-backend and prp-ci-rehearsal-web) cannot be confused with prp-release. No credentials, DB backups, runtime configuration or other workspace paths are collected. Existing main/dev and other PR job commands are unchanged; all added output-producing steps are PR #412-only. No production workflow edits or new permissions.

Next inspect actual artifact availability and metadata, compare run ID, attempt and checkout SHA across both outputs; retain complete CI evidence. If approved, assemble in a disposable runner using the existing package-release.py with a verified exact checkout and validate release manifest, embedded migration policy and hashes. Do not promote rehearsal artifacts, download to a production host, invoke deploy or remove tests. A separate reviewed change would be needed to adapt the production builder; actual savings must be measured. The dedicated PR condition should be removed together with temporary rehearsal steps or replaced by a reviewed nonproduction policy before any final integration.

## Stage 2: same-attempt assembly (temporary experiment; not integration-ready)

Prior run 45543025648 produced both real archives; backend ID 14989858965 (82,886,159 bytes), web ID 14989684030 (615,774 bytes). The overall run initially failed mcp-staging-runtime with Maven Central HTTP 429; both build jobs and staging-contract tests passed. A targeted retry does not make earlier attempt artifacts equivalent to later-attempt artifacts. Never mix attempts.

The new isolated job needs the five selected CI jobs, downloads only the two named outputs of the same run, checks complete manifest/file sets, actual tested checkout SHA, run/attempt, source tree, file sizes and hashes, restores only fixed outputs into a fresh checkout, and invokes the existing repository packager. It never executes the downloaded JAR, contacts a host, or uploads a production prp-release artifact. The result is named prp-ci-rehearsal-assembled with a 3-day retention and a permanently nonauthorizing summary. Its success is not full CI or release eligibility. Existing full CI still must finish successfully. Cross-run/attempt, incomplete or changed outputs require a fresh full rehearsal, not a waiver. The download action's ZIP digest check is not independently reimplemented here; local manifest hashes are not signatures. The previous standalone raw-ZIP reviewer remains separate for actual Deploy PRP artifacts.

**Integration blocker:** the new job is #412-only. A skipped job on main would violate the existing all-jobs-success policy. Remove this temporary job and all temporary output-producing steps before any dev/main integration, or separately review an equivalent production policy. No merge of this experiment is authorized.

## Stage 2 result and cleanup (2026-11-25)

**PASS in disposable CI, NOT a production release.** Exact rehearsal PR head `9c81438bada38486bd2c5ea7bcf637a74f579afd`, actual checkout/merge SHA `def802b4b4ae73122b18ddd9a531a909fb81bd7c`, base dev `76aa550b4b6ab3124846d384ce19aa445071aa8c`. [CI run 45554980221 attempt 1](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45554980221): 35/35 jobs succeeded; [assembly job 139005319244](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/45554980221/job/139005319244) downloaded both same-attempt artifacts, verified their declared payloads and reused the existing package-release.py. Logs report release ID ci-rehearsal-r45554980221-1, tested commit def802b4b4ae73122b18ddd9a531a909fb81bd7c and expected Flyway V30. Neither input artifact was executed. The observed archive is a rehearsal artifact, not the actual deployed schema or production-ready prp-release.

| Artifact | ID | ZIP bytes | GitHub ZIP SHA256 |
| --- | --- | ---: | --- |
| prp-ci-rehearsal-backend | 14995361409 | 82886376 | 907073b12cb95206e0e6347532555a7f1ab372e6f4865382d661c42a47d8b607 |
| prp-ci-rehearsal-web | 14995087289 | 615772 | 6406dd24c5a82f450a3e3070f1452dccf0fcad23b90349fec8ce55b8c7ba96c6 |
| prp-ci-rehearsal-assembled | 14995242169 | 83447800 | d2b7505e52a50b0a578e283ae80c37c1b0e9b07dc4dcf0c8291cfe8e2cf163da |

The assembly step took 3s, download steps 4s + 1s, upload 4s; backend packaging after tests took 6s, final Web production build 12s. This is a single runner sample; does not establish end-to-end production time savings or actual production artifact equivalence. Artifacts expire after three days; archive metadata and runner logs, not independent local bytes, were inspected. The previous CI 45543025648 attempt 2 had 34/34 success but the API actually re-executed all jobs after the targeted retry, and its named artifact metadata still identified earlier uploads; do not infer attempt linkage from GitHub listing alone.

**Clean integration candidate:** remove all PR-number-specific output steps, the temporary assembly job and its two helper scripts and two test files from the proposed integration tree. Keep the immutable rehearsal source and tests in Git history at `9c81438bada38486bd2c5ea7bcf637a74f579afd`, this evidence and the independent offline release artifact reviewer. Restore CI file exactly from pre-rehearsal head `11f736784ef0a094f1141582dbefe9d5f33e4f40`; no permanent job can be skipped solely due to PR number. The new clean HEAD must pass its own 34-job CI and contract checks. No automatic production reuse is activated. A future separately reviewed change must define a general trusted build-artifact policy, prove same-attempt source and exact artifact/controller compatibility, and measure actual savings before replacing any Deploy PRP build/test steps. No production deployment, hold or approval changes.
