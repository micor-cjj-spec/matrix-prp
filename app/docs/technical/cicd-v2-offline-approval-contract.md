# CI/CD V2 P3 — offline approval contract (Issue #323)

## Scope and trust boundary

This is a synthetic, in-process rehearsal only. It imports the accepted P2 release evidence inventory but does not authenticate real people, read GitHub, touch a host, store real approvals or invoke an execution callback. No CLI, API route, MCP tool, workflow dispatch, credential, production environment, production hold edit or deploy integration. Existing production workflow remains authoritative and unchanged. All returned eligibility/authorization/live flags are always false.

## Contract

The candidate snapshot is exact: repository, main SHA, release tar SHA256, schema, artifact ID, action `promote`, CI run/attempt, risk classification, artifact, stage, migration and backup/restore references. Every receipt is explicitly synthetic; P2 must report six pre-approval gates as pass, hold clear with same SHA, no injected approval/publish/smoke receipt. The high-risk class requires a candidate-bound separate synthetic specialist review. Canonical JSON SHA256 binds the complete snapshot. No request may be approved or consumed if its current asserted snapshot has changed, including the exact CI attempt, evidence references or hold.

| Transition | Synthetic actor | Condition |
| --- | --- | --- |
| REQUESTED | chat | exact reviewable snapshot; max 15 min expiry |
| APPROVED | owner | same digest and current snapshot; before expiry |
| REJECTED | owner | active request only; terminal |
| EXPIRED | clock | expiry reached; terminal |
| SIMULATED_CONSUMED | controller | approved, same digest/current snapshot, separate environment reviewer receipt bound to approval ID and digest; before expiry; terminal |

The mutex serializes transitions; a second consume or duplicate request for the same commit/tar digest/action is rejected in the same rehearsal instance. Audit events contain sequence, time, synthetic actor and binding digest; returned objects are defensive copies. Time is an injected synthetic integer; rewind is rejected. No sensitive free-form audit text is accepted.

## Limits and later phase

Memory-only state is deliberately not a durable ledger. A restart or another process has no knowledge of the previous approval; this is **not** a real replay guard. The candidate fingerprint is integrity binding, not a signature or identity proof. Caller-provided synthetic timestamps, actors, evidence and environment receipts are not authenticated. No real approval can be inferred from a successful test. Future separate authorization must precede persistent transactional storage, independently authenticated owner/environment approvals, authoritative evidence collectors, expiry using trusted time, durable audit and atomic outbox/controller handoff with idempotency. Do not enable real production execution, generic Shell, approval/dispatch routes or bypass hold; real staging #396 and production release gates remain independent. Verify independent review and exact-head CI before any further integration decision.

## Verification

`python3 -m unittest discover -s app/scripts -p test_release_approval_contract.py -v`

The tests exercise successful simulation, exact identity/receipt binding, duplicate/replayed and concurrent consumption, expiry, rejection, clock rewind, changed CI attempt, hold, failed/skipped/missing gates, digest/schema mismatch, specialist review, independent environment review, invalid mode/action and mutable returned state. No live data is used.

## P3.2 — disposable persistence rehearsal

The in-memory engine remains the single transition authority. A separate standard-library SQLite adapter serializes its bounded state inside BEGIN IMMEDIATE / COMMIT, shared across synthetic processes using the same private local scratch directory. The directory must be a private owner-only direct child of the OS temp root named prp-p3-rehearsal-*, and the database filename is fixed. Foreign DBs, symlinks and unexpected ledger records fail closed. Maximum 128 records and 2 MiB serialized state; one bounded JSON row is intentional for the rehearsal, not a proposed production data model. It persists request/approval/terminal state, clock, candidate uniqueness and audit together, returns only after commit, rolls back failures, and commits an expiry discovered during a denied operation. Concurrent processes cannot both consume the same record. Audit is transactionally preserved, not independently tamper-evident or append-only. No database server, application migration, secrets, service integration, dispatch or live execution.

Twelve additional synthetic tests cover reopen/restart, distinct processes competing to consume, durable expiry/reject/replay, rollback, stale snapshot, capacity, invalid paths, foreign database and forged authorization flags. The file is local scratch, not a secure multi-host database; deleting or restoring it resets history, OS/file access is trusted and a compromised process can forge synthetic state. Trusted identity, authoritative evidence, durable production-grade audit/idempotency, database backup/restore and external handoff remain separate work. No real approval or production authority is established. The earlier memory-only limitation still applies to the original in-memory engine, not to this bounded scratch adapter.
