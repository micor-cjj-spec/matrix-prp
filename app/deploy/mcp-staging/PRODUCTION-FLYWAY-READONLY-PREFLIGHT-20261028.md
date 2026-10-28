# Production Flyway history preflight — offline, read-only, unapproved (2026-10-28)

> **This is an evidence collection / offline diagnosis procedure, NOT a release
> or access authorization.** PR #113 is Draft. G0/B2 are NO-GO.
> No real server was queried by the development work on this document.
> Do not paste credentials, task rows, personal records, signing secrets,
> database dumps or raw service logs into GitHub, CI artifacts or chat.

## Why this is necessary

[Disposable populated MySQL upgrade CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40608149044)
passed genuine original V1–V24 Flyway migration, preserved synthetic
existing business records, and applied V25–V28. However:
- The GitHub `main` V1–V24 SQL blobs were equal to this Draft at the
  time of the test. **That is source compatibility only.**
- **Operator-provided live SELECT evidence (2026-10-28)** established the
  current production `matrix-mysql` / `matrix_prp` table has **18 successful
  records**, starting with rank 1 / V7 / type `BASELINE` /
  `<< Flyway Baseline >>` / NULL checksum, followed by uninterrupted
  SQL V8–V24. Rank 18 is `V24__vocal_song_library_and_assignments.sql`.
  This exactly matches the *shape* of the project's documented V7
  legacy-baseline transition, not the fresh V1–V24 migration shape.
  **Recorded production SQL checksums have NOT yet been independently
  compared**, and prebaseline V1–V7 DDL is not attested. No live SQL
  modification, installation, or copy restore took place.
- The live *legacy isolated MCP staging* database has an **incompatible**
  V24 MCP drafts lineage; do **not** point the new backend to that volume.

## Independent operator steps (only after authorizing the read)

1. Use the existing protected production access/change-control process.
   Independently verify the database target really is the existing
   PRP production schema; do not infer it from Docker names or Github
   source. Use an existing read-only SQL console/login with **SELECT
   access only**. Do not grant new privileges or use a root session
   solely for this review.
2. Review and run only the single `SELECT JSON_OBJECT(...)` statement in
   [`production_flyway_metadata_readonly.sql`](production_flyway_metadata_readonly.sql).
   The SQL selects `DATABASE()`, migration `installed_rank`,
   `version`, `type`, `script`, `checksum`, and `success`. It does
   **not** read business tables, passwords or OAuth records, and does
   not issue `UPDATE`, `INSERT`, `ALTER`, or `FLYWAY REPAIR`.
3. Verify the one JSON result contains **only migration metadata**.
   Store it locally in a private, access-controlled file (example
   `production-flyway-metadata.private.json`); do not commit or
   publish it. Do **not** expose the SQL connection URI or credentials.
4. Run the offline reviewer from the **exact independently reviewed
   PR #113 revision**:

   ```bash
   python3 app/deploy/mcp-staging/review_production_flyway_history.py \
     --input /path/to/production-flyway-metadata.private.json \
     --expected-schema matrix_prp
   ```

   Supply `--expected-schema` only after independently establishing
   the actual target database name. The reviewer itself has **no
   database client and no network access**, reads local metadata only,
   and emits a coarse verdict without echoing source input rows,
   checksums, filenames, paths, or any raw data.

5. Treat result codes precisely:
   - **Exit 2**: blocked or malformed history. The report gives a
     bounded reason category, not sensitive row detail.
   - **Exit 3**: version 24 or 28 history *shape and filename
     sequence* matches the Draft (either a full fresh V1+ SQL sequence
     or exactly one rank-1 V7 BASELINE followed by SQL V8+). The
     Flyway checksums were **not checked** and **no upgrade is approved**.
   - There is deliberately **no exit 0 approval path**.

   For an additional **source-checksum diagnostic**, run the **same**
   command with `--verify-source-crc` while using the exact independently
   reviewed PR #113 Git commit. This computes reference CRC32 values from
   the checkout's V1–V28 SQL files **without reading any database**,
   and compares them to the supplied Flyway metadata:

   ```bash
   python3 app/deploy/mcp-staging/review_production_flyway_history.py \
     --input /path/to/production-flyway-metadata.private.json \
     --expected-schema matrix_prp --verify-source-crc
   ```

   - **Exit 2**: mismatch (including any script CRC change) or invalid
     history; **stop**. No migration permission.
   - **Exit 4**: all *recorded SQL migrations* (V1+ on fresh databases,
     V8+ after a V7 legacy baseline) match the current reviewed
     **source checkout**, **not** an attested production JAR.
     A V7 BASELINE has no checksum; the source CRC comparison can
     **never** verify its prebaseline V1–V7 schema/DDL. This remains
     `REVIEW_ONLY`, `deployment_permitted=false`, and does **not**
     approve installation.
   - **Exit 3**: shape match but checksum comparison **not requested**.

   [Actual disposable MySQL parity CI 40610322642](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40610322642)
   **SUCCESS**: all **28** CRCs computed by the offline implementation
   matched the real Flyway `flyway_schema_history` generated on
   disposable MySQL 8.4 after real Flyway V24→V28 migration, and the
   reviewer returned **4**, deliberately not 0. It also preserves the
   older `--verify-source-crc`-absent behavior (exit 3).

   **No trust shortcut:** verify the reviewed Git commit and deployed
   artifact SQL contents independently; an arbitrary edited SQL checkout
   is **not** a trusted CRC reference. A separate independent review
   must validate the actual production table DDL and full migration
   lineage against a **restored copy**, and attest backups/rollback.

## Known errors that must STOP the rollout

- A different V24 script (for example, legacy isolated stage
  `V24__mcp_write_drafts.sql`).
- An older, incomplete, or partially applied MCP history; any V25–V27
  state without the full V28 expected chain.
- Failed, baseline-only, *unexpected* baseline or unversioned history
  entries, missing ranks, duplicate versions, reordered installs or
  unknown scripts. The sole permitted baseline shape is rank-1
  V7 `BASELINE` / `<< Flyway Baseline >>` / checksum NULL followed
  by contiguous SQL V8 up to V24 or V28.
- Wrong schema; MySQL connection failure; invalid metadata export;
  absent checksum on any SQL record; any checksum mismatch in the independent
  official Flyway validation.
- Any environment whose operator cannot attest the origin, backup
  and data recovery process.

**No shortcut:** Never rewrite `flyway_schema_history`,
`repair`, `clean`, `baselineOnMigrate`, or replace the original
production MySQL volume to force the preflight to pass. Running an
offline report does not substitute for G0/B2 scope authorization,
verified independent restore rehearsal, Keycloak registration or a
real ChatGPT `prp_tasks_list` user-owned data call.

## Production lineage interpretation and hard boundary

The first live production query returned 18 rows / latest V24 / no failures.
A subsequent live, password-prompted read-only SELECT established the **exact**
V7 baseline then V8–V24 SQL sequence. These are operator-reported MySQL
results, not a cryptographically signed independently restored artifact.
The private V8–V24 Flyway checksums still need a separate offline source-CRC
review on the approved PR commit.

The offline reviewer has two **non-interchangeable** accepted shapes:
1. New database with SQL V1…V24 or V1…V28, all checksums present.
2. Existing production-style database with exactly rank-1 V7 BASELINE,
   checksum NULL and the default Flyway baseline description, then SQL
   V8…V24 or V8…V28, all SQL checksums present.

The reviewer must **never** pretend the V7 baseline validated old SQL
V1–V7, assume their DDL matches, or turn a matching V8–V24 checksum
into release authorization. Backup recovery, actual production
`flyway_schema_history` attestation, copied schema review and separately
approved G0/B2 remain required. Do not create, repair, move, or rewrite
any database history rows to fit either shape.

## CI-only proof

[Actual isolated MySQL legacy V7 baseline to V28 CI 40633804543](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40633804543)
**SUCCESS** (2026-10-28): inside a freshly created runner-owned
`mysql:8.4` container, built V1–V7 synthetic legacy-equivalent tables,
discarded **only that disposable schema's** Flyway history, explicitly
recorded one default V7 baseline, then applied 17 SQL migrations V8–V24
and 4 SQL migrations V25–V28. It verified exactly 18 V24 history rows
and 22 V28 rows, the rank-1 baseline/checksum NULL, preserved
synthetic users/tasks/finance fingerprints, and verified SQL V8–V28
source CRC via the same SELECT-only metadata exporter and offline
reviewer. Results were strictly non-zero REVIEW_ONLY exits 3 and 4,
`legacy_baseline_v7=true`,
`prebaseline_v1_v7_schema_verified=false`,
`deployment_permitted=false`. The CI did **not** access production
or restore a real production backup.

[Offline V7-baseline strict negative tests 40633544002](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40633544002)
**SUCCESS**: 27 synthetic tests covering exact baseline shape, tampering,
missing rows, wrong types, duplicate/out-of-order entries, source CRC
mismatch, and fail-closed release status.

[Offline negative contract CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40609387782)
ran a synthetic report matrix with failures for baseline/failed
migration, old stage V24 script, partial history, wrong schema,
missing rows, duplicate ranks, malformed metadata and secret-safe
output. No production SQL was executed.
