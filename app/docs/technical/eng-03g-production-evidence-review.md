# ENG-03G · Independent evidence intake and production hold dossier

**Status: review-only, production publication BLOCKED by design.** This work is
stacked after PR #101 and its predecessor PRs #96–100. Do not merge to
`main` merely because synthetic CI is green; a merge may trigger the trusted
main publication workflow.

## Problem

The PR #100 executable-JAR HTTP receipts establish only that two GitHub CI
builds run against **synthetic MySQL 8.4**. PR #101 offers a
**not-yet-installed, administrator-reviewed proposal** to collect a bounded
local host report. Neither is proof that the active PRP server runs the
GitHub `main` JAR, nor that its old binary would survive an actual database
migration.

This stage adds `app/deploy/review_release_evidence_bundle.py`, a
**strict, completely offline** evidence comparison. It accepts six
*separately obtained* files:

1. A host collector's bounded `host-observation.json` (format from PR #101).
2. Byte-exact `release.json` for the purported currently deployed release,
   obtained through separately approved provenance.
3. The already-reviewed controller manifest from the **appropriate** source
   revision.
4. Byte-exact `release.json` for a separately reviewed candidate release.
5. A PR #100-style baseline CI JAR HTTP receipt.
6. A PR #100-style candidate CI JAR HTTP receipt.

Example **only on a trusted offline review workstation**:

```sh
python3 app/deploy/review_release_evidence_bundle.py \
  --host-observation /review/host-observation.json \
  --deployed-release /review/deployed/release.json \
  --controller-manifest /review/controller-manifest.json \
  --candidate-release /review/candidate/release.json \
  --baseline-ci-receipt /review/ci/prp-baseline-jar-http.json \
  --candidate-ci-receipt /review/ci/prp-candidate-jar-http.json
```

Inputs are capped and loaded with duplicate-JSON-field rejection. Any missing
field, forbidden extra field, tampered controller hash, candidate JAR digest
that differs from its corresponding CI receipt, reversed schema version,
identical candidate/old identity, false `production_authorized` flag, skipped
HTTP probe or outdated collector report causes **`EVIDENCE_REJECTED`** with
exit status 2. No user-supplied path or content is echoed on errors.

A technically consistent set **still** returns
`classification: PRODUCTION_REVIEW_BLOCKED`, plus
`publication_gate_passed: false` and
`production_authorized: false`. The report contains only accepted commit
SHAs, JAR digests, SHA256 of the six supplied inputs and status codes.
No names, emails, authentication tokens, content rows or filesystem paths
are copied out. SHA256 binds submitted bytes but does **not** independently
authenticate their source or acquisition channel.

## Important: baseline mismatch is not a trivial CI failure

The CI baseline is a checkout of `main` at CI time. Production may still
be on a **different, older release**. The checker identifies this as
`BLOCKED_BASELINE_NOT_RUNNING_RELEASE` rather than silently equating them.

Even if its hash matches the observed JAR, the status is
`CI_ONLY_BASELINE_DIGEST_MATCH_UNATTESTED`. It is not evidence that the
collector was actually run on the server, that the running JVM originally
loaded those unchanged bytes, or that this was the previous production
release. No boolean in the input can promote this evidence to approval.

## Non-negotiable production gates

The machine report enumerates P1–P9 from ENG-03C: real backup authenticity,
isolated restored rehearsal, actual MySQL/DDL verification, real lock/traffic
measurement, authentic old/new JAR+Web compatibility, exact Flyway SQL and
artifact provenance, reviewed root-controller patch, independent root/SSH
attestation, and post-cutover integrity. **All nine remain unverified or
blocked in ENG-03G**. A successful CI test has no mechanism to turn them green.

Next human work, in order:

- Obtain actual server running release/JAR/process identity using a separately
  reviewed and authorized fixed-path, root-only measurement process.
  Independently verify its source, operator, host identity, execution time,
  and secure chain of custody. Do **not** install new privileged SSH commands
  or export raw systemd arguments, Java configs, logs or keys.
- Obtain an independently trusted previous release artifact. Do not assume
  the latest Git commit or CI baseline equals it.
- With DBA authorization, restore a complete, authentic backup on **physically
  isolated infrastructure**, compare row/tenant/media fingerprints, rehearse
  the exact SQL and run the actual previous and candidate JARs on the
  expanded restored copy with authenticated HTTP workflows.
- Have the administrator and DBA separately review controller upgrade,
  database locking, failure recovery, publication hold and rollback.
  Retain the existing `create-empty` policy until then.

## Explicit non-goals and safety boundaries

There is no remote command, network connection, database connection, SSH key,
publication approval, new Flyway migration, V24, JAR deployment, root
controller install, manifest alteration or runtime service restart in this PR.
The offline tool **never** makes production available merely by supplying JSON
with plausible hashes. Its report is advisory and must not be wired as an
automatic `publish_allowed` or environment protection override.
