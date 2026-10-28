# PRP production V24 → V28: owner-FK and new-object DDL metadata preflight

> **REVIEW ONLY, NOT A RELEASE OR SCHEMA MIGRATION.** No production DB
> writes, backup, data copy, OAuth activation or Nginx modification is
> authorized. G0/B2 remain NO-GO; Draft PR #113 is not installed.

## Why this next test is needed

On 2026-10-28 the operator ran the **actual production**
`matrix-mysql` / `matrix_prp` pinned Flyway CRC aggregate SELECT.
It returned `schema_match=YES`, `history_rows=18`,
`baseline_rows_matched=1`, `observed_sql_rows=17`,
`source_sql_rows_matched=17`,
`decision=SOURCE_CRC_MATCH_REVIEW_ONLY`,
`deployment_permitted=NO`. This establishes **17/17 original
V8–V24 SQL migration CRC parity** for the reviewed source, but not
the V7-prebaseline DDL or recovery.

Source review of actual proposed V25–V28 SQL proves the new migrations
currently contain exactly **five additive `CREATE TABLE prp_mcp_...`
statements** and five `FOREIGN KEY (user_id) REFERENCES prp_users(id)
ON DELETE CASCADE` constraints:

- V25 `prp_mcp_write_drafts`
- V26 `prp_mcp_client_grants`
- V27 `prp_mcp_identity_links` and `prp_mcp_link_tickets`
- V28 `prp_mcp_oidc_link_flows`

These are needed by the identity link and grant flow. Even a fully
source-matching Flyway history does not prove that the *real*
`prp_users(id)` is a compatible signed `BIGINT` single-column
InnoDB primary key, or that the five proposed table/foreign-key
constraint names are unused. This is the next bounded preflight.

## The fixed SELECT-only check (if independently authorized)

Use `app/deploy/mcp-staging/production_v24_mcp_ddl_shape_readonly.sql`
from a verified immutable Git commit. It requires the active DB be
exactly `matrix_prp`. It reads only `information_schema` metadata
and `flyway_schema_history` **counts**; it does not SELECT from
`prp_users` itself or from any task, finance, account, OAuth, or
private table, and does not issue DDL/DML. It returns **one aggregate
row** with:

| Output | Required for a positive metadata result |
| --- | --- |
| `schema_match` | `YES` |
| `owner_table_innodb` | `1` |
| `owner_signed_bigint_id` | `1` |
| `owner_id_primary_member` | `1` |
| `owner_primary_columns` | `1` |
| `owner_partition_count` | `0` |
| `proposed_table_name_collisions` | `0` |
| `proposed_fk_name_collisions` | `0` |
| `history_rows` | `18` |
| `successful_history_rows` | `18` |
| `proposed_version_history_rows` | `0` |
| `decision` | `V25_V28_FK_DDL_SHAPE_MATCH_REVIEW_ONLY` |
| `deployment_permitted` | `NO`, **always** |

Any other count, missing metadata permission, wrong schema, or
unexpected migration returns `BLOCKED_OR_UNVERIFIED` or a query
error. Do not mutate anything to make the query pass.

**Run from an interactive, independently authorized terminal using
the existing SELECT-authorized `matrix_prp` MySQL login**, with
`-p` interactive password prompt. Do not embed `docker exec -it`
inside a `bash <<'BASH'` heredoc: that previously failed due to
no TTY **before** SQL execution. Verify `FETCH_HEAD == PIN` and
`git cat-file -e PIN:SQL` before running `git show PIN:SQL`.

This SQL has offline tests that compare its **exact five table and
foreign key names** with the actual V25–V28 source. The tests assert
that the query contains a single fixed SELECT, no SQL mutations,
non-business-table scope, fail-closed conditions, and permanent
`deployment_permitted=NO`. Such static CI is **not proof** that
the SQL has been executed successfully against production MySQL.

## What a metadata PASS would and would not prove

A matching result confirms the specific target-user FK type/key/engine
and name-collision preconditions for the five new tables at the
point of observation. It does **not** prove:
- whole V1–V7 prebaseline DDL, current production compiled JAR
  migration bytes, full V25–V28 live execution, metadata privileges
  for the final deploy identity, disk capacity or operational
  transactional safety;
- intact owner/task/finance/vocal/video data after a real restored-copy
  upgrade, or all data created after a rollback point being preserved;
- OAuth client registration, genuine ChatGPT `private_key_jwt`,
  public TLS/Host/SNI/URI routing, first-party browser identity linking,
  or real `prp_tasks_list`;
- G0/B2 authorization, signed recovery receipts or a migration permit.

The next appropriate *technical* step after metadata parity is an
independently approved, isolated restore of the true production MySQL
schema/data and a data-preserving V24→V28 rehearsal, with checked
object counts, task/owner linkage, application startup, rollback
semantics and no production mutations. **Do not run V25–V28 on
the existing production or legacy V2 databases merely because
this SELECT returns positive.**
