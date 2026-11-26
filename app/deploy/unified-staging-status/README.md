# Unified Staging S6 — repository review status (Issue #396)

**BLOCKED / NO HOST ACCESS / NO DEPLOY / NO MERGE.** This is a review-only, point-in-time
machine-readable handoff for CI/CD V2 (#323); it cannot authorize deployment.
It reuses #398 (S0 inventory/report), #400 (isolated Compose), #403 (all-module
CI-only integration), and references #407 as separate V30-only CI evidence.
No feature sources, migration policy, shared workflows, production or older stages are changed.

## Consume the snapshot

`test-env-status.json` records observed GitHub PR head SHAs and Actions run IDs.
Resolve each run as `https://github.com/micor-cjj-spec/matrix-prp/actions/runs/<run_id>`;
compare PR head, run attempt, conclusion and actual checkout/source tree independently
before any candidate review. A PR-head SHA is not necessarily the tested checkout SHA.
Expected Flyway values come from the candidate migration policy; they are NOT a live
database observation. CI browser checks are synthetic, not physical iPhone UAT.

The #403 archive metadata identifies the existing artifact, not individual OCI image
digests or a verified local copy. Its reported expiration is 2026-11-26 04:50:07 UTC.
Do not deploy from a stale/expired/unverified artifact. A replacement candidate must
be rebuilt/reviewed in disposable CI and re-bound to exact source/tree and individual
image digests. No archive was downloaded or installed in this handoff.

From repository root, offline only:

```sh
python3 app/deploy/unified_staging_status.py
python3 -m unittest discover -s app/deploy -p test_unified_staging_status.py -v
```

The validator checks structure and refuses all live assertions, authorizations and
readiness promotions. It does not contact GitHub or a host, prove authenticity or
refresh CI results. Its successful exit means valid *review format* only; the clock
expiry flag is not a live artifact availability query. Existing repository CI's
deployment-test unittest discovery picks up the new tests without workflow changes.

## Next gates (independent, sequential)

| Gate | Required before moving forward |
| --- | --- |
| S0 | Separate named-host authorization; use #398 exact reviewed collector and report validator; independent private host identity, ownership and resource review. |
| S1/S2 | Decide shared-host dedicated Compose versus isolated VM from actual capacity, volume/network/ingress ownership and blast radius. Review #400 config without assuming any port free. |
| S3 | Choose one reviewed candidate; recheck dev drift, source tree, migration checksums and individual image digests. Keep #403 CI-only and #407 Health-only scope distinct. |
| S4 | Separate installation approval, fresh stage-only data/credentials, isolated ingress/TLS, backup/recovery and rollback scope. No production or legacy/V2 replacement. |
| S5 | Real HTTPS/Web/API/Flyway, two synthetic owners and access denial, physical iPhone Safari/PWA, original four tabs, cross-module UAT and stage restore rehearsal. OAuth/MCP remains separately gated. |
| S6 | Review actual evidence before changing this review-only contract. |

Lifecycle vocabulary: proposed = design only; blocked = missing required evidence or
approval; provisioned = authorized persistent resources created; running = actual
runtime health established; verified = independent all-module runtime, isolation,
device UAT and restore evidence for the same candidate. V1 intentionally supports
only the current blocked snapshot; later states require a separately reviewed
evidence contract, not a manual status flip or CI-derived promotion. The true live
state is unknown pending S0. Historical CI success never authorizes stage or production.

Never commit real host identifiers, secrets, raw configuration, personal data or
database dumps. Keep production publication hold, existing ports 11000/18081/18082/
18083, DNS, Keycloak/OAuth, SSH and production workflows unchanged.
