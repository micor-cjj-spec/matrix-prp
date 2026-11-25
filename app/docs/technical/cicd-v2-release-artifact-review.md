# Existing release artifact review (CI/CD V2 #323)

The existing Deploy PRP workflow already supports main CI → release build → prp-release artifact → separately approved promote. Do not add a second production builder or change Deploy PRP, publication hold, or production controller here. This tool only evaluates an existing local copy of an artifact, without extracting it to disk or running its code.

## Offline inputs and output

- expected.json: exact reviewed candidate commit, schema (expected Flyway integer), backend_source (Git tree SHA from git rev-parse HEAD:app/backend), web_source (SHA256 of git ls-tree HEAD app/web app/scripts app/config, exactly as package-release.py computes). Independently obtain these from an immutable reviewed checkout, not from the archive itself.
- snapshot.json: object containing run (GitHub Actions run response), jobs (complete attempt-specific jobs response), artifacts (complete run-specific artifact listing). Obtain using authorized read-only GitHub API for a completed same-repository main workflow_run Deploy PRP run. No partial lists, branch PR, manually dispatched build, expired or ambiguous artifact. Verify current main and latest exact main CI separately with existing release-readiness precheck. A successful run does not imply publish succeeded.
- archive.zip: the raw GitHub artifact ZIP bytes, not gh run download's extracted release.tar.gz. GitHub archive digest and inner tar digest are distinct. The tool checks both the outer digest and the per-file manifest, candidate source/version, embedded release ID/run attempt and migration-policy commit. It never treats a GitHub archive digest as an OCI image digest or as the release tar digest.

    python3 app/scripts/release_artifact_review.py --expected expected.json --snapshot snapshot.json --archive archive.zip --output artifact-review.json

The report's artifact_evidence can be manually supplied to release_evidence.py with the same commit, release_tar_digest and schema. All metadata remains caller assertions; the local byte match does NOT independently prove the GitHub metadata, main CI causal linkage, actual jar migration content, SQL policy validity, staging/runtime, production controller compatibility, or permission to reuse/publish. The existing packaging and controller validators must still run. In particular, do not mistake a skipped publish for LIVE. This proposal does not invoke promote, remove a hold, perform a network request, or download any artifact.

## Next step

After CI validates synthetic fixtures, independently review a real unexpired candidate in an authorized non-production workspace and compare current production build requirements to CI job coverage. Reuse the existing promote path only after explicit owner approval and all existing gates. No deletion of redundant tests or measurement of build savings until equivalence is demonstrated. No production release is authorized by this contract.
