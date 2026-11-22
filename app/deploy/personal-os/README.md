# Personal OS V1 independent preview — OFFLINE evidence gate

**Review only, no installation, network traffic or deployment authority.** This directory checks a *redacted declaration* of a separately approved preview against an exact candidate Git source checkout. Passing the checker means only `DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED`, **not that any real host/database/client is isolated or deployed**. If evidence is missing, the result is `NO_GO:<sanitized code>` and exit code 2.

## Before attempting preview

- Obtain a **separately approved** independent host and dedicated HTTPS hostname, check real DNS/TLS/vhost/ports and ensure no production/MCP V2 shared services are touched.
- Use a **fresh, empty, unique** MySQL database/volume and Compose project; test users must be synthetic. Never reuse production `matrix_prp`, existing `matrix_prp_mcp_stage`, an existing stage volume, live owner information or production secrets.
- The candidate must have reviewed **Health V30 followed by Personal OS V31**, each with exact committed SQL SHA256 in `app/deploy/migration-policy.json`. This checker reads that policy and both SQL files but never runs migrations. The current `dev` lacking those revisions **must fail**.
- MCP, OAuth/Keycloak first-party linking, automatic chat extraction, model outbound requests and MCP write privileges remain OFF. Owner-reviewed first-party tests with synthetic fixtures are a separate explicitly authorized UAT.
- A **real independently verified operator attestation** is needed; simply putting `true` into a JSON field is not proof. Preserve read-only inventory/receipts privately and redacted; do not publish IPs, secrets, full server configuration, private data or credentials.

## Example invocation (no real values)

```sh
python3 app/deploy/personal-os/preview_gate.py \
  --evidence /secure/redacted-personal-os-preview-evidence.json \
  --expected-sha <40-char-exact-reviewed-candidate-commit> \
  --candidate-root /path/to/reviewed/candidate/checkout
```

The evidence file is strictly limited to fields named in `preview_gate.py`. There is intentionally **no sample passable attestation** in the repository: a fake green self-report must not be copied into a real host approval. Schema is `personal-os-preview-v1`, with `stage` and `observed` objects. The checked gateway port and hostname are **claimed values, not checked host resources**; image digests and source SHAs are format/equality checks against claims, not independent image verification.

## Offline tests

```sh
python3 -m unittest discover -s app/deploy/personal-os -p 'test_preview_gate.py' -v
```

The top-level `app/deploy/test_personal_os_preview_gate.py` shim also exposes all 29 tests to the existing generic `app/deploy` CI discovery. No live network, Docker, MySQL or user data is used.

## Deployment status

Tracking: [T-009 #301](https://github.com/micor-cjj-spec/matrix-prp/issues/301), [T-007 #188](https://github.com/micor-cjj-spec/matrix-prp/issues/188). This work is **not** a runtime source integration, release, iPhone UAT, real provider privacy consent or owner approval. Keep `publication-hold.json`; never merge this Draft as a shortcut to deploy or change main/dev, production/MySQL, existing MCP V2, Keycloak, OAuth scope or ChatGPT grants.
