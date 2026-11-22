# Health V2: isolated staging evidence preflight (REVIEW ONLY)

**This command does not connect to or modify any host, database, OAuth realm, GitHub environment or production service.** It checks the consistency of a *redacted operator-supplied declaration*, not actual live safety or release authorization.

Existing known environments are distinct and must not be overwritten:

- 18081: legacy task-only staging template.
- 18082: existing shared V2 gateway with 8 advertised OAuth scopes and write-enabled overlay in an earlier read-only operator report.
- 18083: review-only fresh-MySQL proposal; not proof of deployment.
- 11000 / matrix_prp: existing production backend/database.

## How to use

1. An authorized staging operator independently records the *actual running* source commit, backend/web source commits and image digests, Flyway history/version, dedicated database and realm, HTTPS host identity and non-production isolation. Do **not** copy raw docker inspect, Nginx output, environmental variables, passwords, tokens, user IDs, photos or database records.
2. Create a **local private** JSON file with the keys below, leaving all unverified values null or false until independently observed. Never commit a completed real-world manifest or credentials.
3. Run the offline preflight **from the exact reviewed candidate checkout** with its matching `app/deploy/migration-policy.json` and source SHA. The expected Flyway version is derived from this checked-in policy: a Health-only V30 branch expects 30, while the combined Health V30 + Personal OS V31 candidate expects 31. Do not reuse an older checker or allow a partially migrated DB to pass:

       python3 app/deploy/health-v2/readiness_audit.py --evidence /private/redacted.json --expected-sha <reviewed-40-hex-health-commit>

4. BLOCKED:CODE means stop. DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED confirms **only that the operator's claims are mutually consistent**; it is **not** a verified deployment, UAT PASS or permission to touch OAuth or live data. A distinct reviewer must confirm the observations and approvals.

The parser **rejects duplicate JSON keys and unknown fields** (including extra purported approvals) rather than ignoring unreviewed assertions. It also refuses a missing, malformed, duplicate-version or Health-V30-free migration policy, and compares the observed highest Flyway version against the policy in the reviewed checkout, not a hard-coded V30. The evidence schema is exact for version `health-v2-stage-readiness-v1`; adding an attestation field requires a separately reviewed schema and tests. Never use a successful offline JSON check as proof of a live observation.

### JSON structure (deliberately incomplete / must fail until verified)

    {
      "schema": "health-v2-stage-readiness-v1",
      "stage": {
        "kind": "dedicated-health-v2",
        "public_host": "health-v2-stage.example.net",
        "oidc_host": "auth-health-v2-stage.example.net",
        "gateway_port": 18084,
        "database_name": "prp_health_v2_stage",
        "db_isolated": false,
        "oidc_isolated": false,
        "test_identities_only": false,
        "owner_approved": false,
        "production_mounts_present": null,
        "production_data_used": null,
        "shared_v2_modified": null
      },
      "observed": {
        "source_sha": "REPLACE_WITH_REVIEWED_SHA",
        "backend_source_sha": "REPLACE_WITH_OBSERVED_SHA",
        "web_source_sha": "REPLACE_WITH_OBSERVED_SHA",
        "backend_image_digest": "REPLACE_WITH_OBSERVED_SHA256_IMAGE_DIGEST",
        "web_image_digest": "REPLACE_WITH_OBSERVED_SHA256_IMAGE_DIGEST",
        "flyway_version": null,
        "flyway_failed_count": null,
        "https_hostname_verified": false,
        "oidc_issuer_host": "auth-health-v2-stage.example.net",
        "write_enabled": null,
        "actual_runtime_observation": false
      }
    }

Initial readiness requires write_enabled=false, a separate test-only stack and real operator approval. Subsequent write/ChatGPT approval UAT needs its **own** independent change approval and rollback plan; this tool intentionally never enables write operations.

Run synthetic offline tests:

       python3 -m unittest discover -s app/deploy/health-v2 -p 'test_*.py'

Relevant release gates: Health staging S01–S09 #178, physical iPhone P01–P10 #177, release #260. Exact-head CI of synthetic Health #279 (35/35 green) cannot substitute for a real isolated staging deployment or encrypted production V29 backup recovery.

**DO NOT MERGE or DEPLOY this CI/review artifact. Release remains NO-GO.**
