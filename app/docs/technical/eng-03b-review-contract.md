# ENG-03B · Existing-table expansion: reviewer evidence contract

> **Review-only capability. Not a production migration path.**
> This PR depends on ENG-03A (PR #96). It neither changes `migration_policy.py` nor
> the independently installed root-owned controller, and it adds **no Flyway V24**.
> An otherwise-valid ALTER still fails the current `create-empty` production gate.

## What the machine-checkable contract proves (and does not prove)

`app/deploy/expand_review_contract.py` checks a **candidate** for one
`ALTER TABLE prp_* ADD COLUMN ... NULL, ALGORITHM=INSTANT;`. Its inputs are:

1. Candidate SQL bytes: sha256-bound to the exact proposed statement.
2. A strict JSON contract: source Git commit SHA, old/next migration version,
   MySQL family 8.4, targeted table/column/type, fingerprints for old columns,
   rows, indexes, constraints and triggers.
3. A *before* schema/data fingerprint snapshot.
4. An *after* snapshot from a **separate, isolated database rehearsal**.

The verifier rejects mismatched SQL/commit/versions, old-row count or full-old-row
hash changes, changes to existing column metadata, indexes, constraints or triggers,
and any new-field non-NULL values on historical rows. It requires the new field
to be appended, nullable, with no explicit default and no unexpected extra
attributes. Duplicate JSON keys and unrecognized fields fail closed.

Example **offline only**:

```sh
python3 app/deploy/expand_review_contract.py \
  --sql /review/candidate.sql \
  --contract /review/contract.json \
  --before /review/pre.json \
  --after /review/post.json
```

Successful output says `READY_FOR_SPECIALIST_REVIEW`, always with
`production_authorized: false` and `controller_upgrade_required: true`.
**Neither a SHA256 nor passing tests constitute authorization or provenance.**
The tool neither connects to databases nor runs SQL; a reviewer must establish
the actual origin of supplied fingerprints, server identity and migration version.

## CI proof and its limitations

The existing MySQL 8.4 integration job now captures real
`information_schema.COLUMNS`, `STATISTICS`, table constraints, triggers and
existing row bytes (the *synthetic three-column test table*, not customer data)
before/after applying a review candidate. It verifies an actual read-back, not
self-declared `after` evidence. A separate unit-test suite rejects tampered
commit, schema, ownership/row digests, indexes, constraints, foreign-key
metadata, additional columns, malformed JSON and forged approval.

For CI, the Git SHA and Flyway version are intentionally synthetic (`a` × 40,
V23 → V24). They are **not** attestation of the real production version. This
test does not exercise production table scale, metadata-lock waiting, backup
restoration, concurrent user writes, real rollback or cross-version service
operation; those must be separately tested before any production controller
capability change. Index and constraint fingerprints cover the isolated test
schema only, not an inventory of all real production objects.

## Mandatory production controller and DBA review for a future ENG-03C

- **Controller:** independent approved installer, exact on-host SHA256 and
  deployment boundary attestation; no broadened SSH, root, SFTP or GitHub
  Actions permissions. Existing `create-empty` rules remain immutable.
- **Release binding:** exact source commit, signed-off SQL digest, expected
  old table definition, application versions and a new **separately reviewed**
  production-compatible preservation mode. Hold application publication
  during controller upgrade and confirm controller-only rehearsal first.
- **Database:** verify actual MySQL version, existing schema/Flyway version,
  duplicate-column absence, storage engine, column/row/index/foreign-key
  invariants and full data fingerprints on a restored representative backup.
- **Lock and performance:** measure metadata-lock wait, DDL duration, active
  traffic and failure handling. `ALGORITHM=INSTANT` does not remove metadata
  locks. Reject unsupported table formats/constraints and require a rollback
  decision *before* the maintenance window.
- **Backward compatibility:** old and new application versions must both
  tolerate the additive field. Backfill in separately approved, checkpointed
  batches; field renames/drops are a later specialist review.
- **After release:** store independent schema, table/row/ownership, health,
  release SHA and migration-version evidence; never call a build or merge a
  successful **production deployment** without this proof.

## Application rollback behavior

For an additive nullable column, leave the expanded DB in place and roll back
**only application binaries**, provided pre-tested old binaries remain compatible
with the expanded table. Do **not** run an automatic `DROP COLUMN` or overwrite
a database already accepting new writes with an old snapshot. Actual data
restoration requires its own incident procedure and explicit decision.

## Acceptance for ENG-03B

- Unit tests reject forged contracts and all historical preservation drift.
- Disposable MySQL 8.4 integration verifies metadata and row fingerprints
  against actual database observations.
- Entire existing backend, Flyway, controller compatibility and deployment
  gate suite passes.
- PR remains Draft; do not merge or deploy until PR #96 is reviewed and this
  extension is reviewed. This stage **does not install or authorize ALTER**.
