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
- The operator's current production MySQL `flyway_schema_history`
  has **not** been inspected here. Previous manual migration, baseline,
  failed upgrade or changed checksum would invalidate the synthetic
  migration proof.
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
   `version`, `script`, `checksum`, and `success`. It does
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
     sequence* matches the Draft, but **Flyway checksums remain
     unverified** and **no upgrade is approved**.
   - There is deliberately **no exit 0 approval path**.

   A trusted checksum comparison must be separately performed using
   a genuine Flyway reference from the reviewed built artifact (not
   a guessed checksum). A later independent review must validate
   the actual table DDL and full lineage in a **restored copy**.

## Known errors that must STOP the rollout

- A different V24 script (for example, legacy isolated stage
  `V24__mcp_write_drafts.sql`).
- An older, incomplete, or partially applied MCP history; any V25–V27
  state without the full V28 expected chain.
- Failed, baseline-only or unversioned history entries, missing ranks,
  duplicate versions, reordered installs or unknown scripts.
- Wrong schema; MySQL connection failure; invalid metadata export;
  absent Flyway checksum; any checksum mismatch in the independent
  official Flyway validation.
- Any environment whose operator cannot attest the origin, backup
  and data recovery process.

**No shortcut:** Never rewrite `flyway_schema_history`,
`repair`, `clean`, `baselineOnMigrate`, or replace the original
production MySQL volume to force the preflight to pass. Running an
offline report does not substitute for G0/B2 scope authorization,
verified independent restore rehearsal, Keycloak registration or a
real ChatGPT `prp_tasks_list` user-owned data call.

## CI-only proof

[Offline negative contract CI](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40609387782)
ran a synthetic report matrix with failures for baseline/failed
migration, old stage V24 script, partial history, wrong schema,
missing rows, duplicate ranks, malformed metadata and secret-safe
output. No production SQL was executed.
