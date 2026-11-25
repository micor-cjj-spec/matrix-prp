# P3.7.2 offline signed runtime, database and module UAT receipts (#323)

## Scope and dependency

This is a stacked Draft on P3.7.1 PR #447. It reuses the existing staging
evidence intake, runtime and database validators; it does not copy or modify
those validators. The only new behavior is an offline Ed25519 signed receipt
envelope and strict typed receipt binding.

Receipt roles are distinct: stage operator, database reviewer, backup/restore
reviewer, security reviewer, Health V2 owner, and UI V2 owner. A signer key ID
cannot be reused across roles. Each envelope binds repository environment,
receipt type, key ID, issue/expiry times, nonce, and canonical payload. The
signature uses a domain-separated canonical JSON representation and Ed25519
verification via the local OpenSSL executable (no shell, network, or arbitrary
command input).

## Receipt contracts

- Runtime observation: exact candidate, P3.7.1 projection digest, before/after
  service image and configuration digests, Flyway failure count, and rollback
  plan digest. Runtime observations must bracket module UAT.
- Database migration: exact baseline schema/history/data/source-instance and
  migration-policy digest, expected migration inventory, plus explicit
  apply-migrations or no-schema-change mode.
- Backup/restore: separately signed receipt binding the same database context,
  backup digest, restore target, restored schema/history/data digests, isolation,
  and rehearsal chronology. Existing P3.6 validation checks backup freshness and
  restore-before-migration ordering.
- Risk review: separately signed security reviewer receipt, bound to the same
  candidate and database context; existing P3.6 risk classification and
  specialist review checks remain in force.
- Health V2 UAT: separate owner signature, two distinct hashed ordinary-owner
  identities, zero MCP grants, owner-isolation and nutrition cases, and bounded
  cleanup of owner-created meal records only.
- UI V2 UAT: separate owner signature, six exact UI cases, ordinary non-admin
  identity with zero MCP grants, and desktop/iPhone device observations with
  OS/browser/viewport and evidence digests.

The no-schema-change path is explicit: baseline equals target schema, migration
inventory is empty, and a successful no-op migration receipt preserves Flyway
history. Backup/restore remains mandatory; no migration is not a waiver for
recovery evidence.

## Trust and fail-closed boundary

TRUSTED_SIGNERS is intentionally empty. No production or staging public key is
provisioned by this PR. Synthetic tests create ephemeral Ed25519 keys at runtime
inside temporary directories and destroy them after the test. Private keys,
real account identifiers, business payloads, screenshots, and host configuration
are not stored in the repository.

Even when synthetic signatures verify, the report remains BLOCKED. The contract
does not establish the provenance of a real trust anchor, host attestation,
trusted time, durable cross-bundle replay prevention, actual evidence bytes,
independent human authority, CurrentReview PASS, release eligibility, or deployment
authorization. Nonces are checked only within one bundle; a persistent replay
ledger belongs to a later server-owned phase.

This is a schema/cryptographic-mechanics test, not an activated evidence collector.
No live #396 endpoint is queried or operator receipt is used as a signed test fixture; only synthetic data is exercised. No shared runner is enabled, and no workflow, approval
tool, executor, production hold, branch protection, environment secret, credential,
database, server, or deployment is changed.

## CI

The deployment-gate-tests job runs the synthetic test suite. All tests use only
ephemeral keys and synthetic receipts. Full CI remains mandatory; no gate is
removed, skipped, selectively retried, or weakened.
