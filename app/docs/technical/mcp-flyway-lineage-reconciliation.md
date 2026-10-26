# Reconcile production V24 with the existing MCP staging migration history

## Verified source of the collision (2026-10-22)

- Current `main` production lineage: `V24__vocal_song_library_and_assignments.sql`; production database reported at V24.
- Existing live **isolated** MCP staging database: legacy `V24__mcp_write_drafts.sql`, `V25__mcp_client_grants.sql`, `V26__mcp_identity_links.sql`, all applied successfully.
- Both lineages cannot safely share Flyway V24 with different SQL/checksums. No production database was accessed or changed during this fix.
- The corrected **fresh database** lineage is V24 vocal, V25 MCP drafts, V26 MCP client grants, V27 MCP identity links, followed by V28 MCP temporary client grant expiry. SQL DDL for the original MCP V24–V26 migrations is preserved byte-for-byte; those original migration identities were moved to V25–V27.

## Additional source inventory (2026-10-25)

The feature branch includes `V28__mcp_temporary_client_grant_expiry.sql` in addition to the V24–V27 corrected lineage. Older text that ends at V27 is incomplete and must not serve as the deployment checklist. Confirm the migration directory and `flyway_schema_history` immediately before a fresh-schema acceptance run; do not infer a deployed V28 from source presence alone.

## Deployment STOP gate (fail closed)

**Do not run a backend built from this branch against the existing staging schema.** Flyway validation should reject the previously applied staging V24–V26; bypassing that validation is not a resolution. Do not `flyway repair`, set `outOfOrder` or `baselineOnMigrate` casually, edit Flyway history, drop/rename an existing data volume, or use a production connection.

The production database also cannot be treated as a clean database. Before any eventual production release, prove a controlled **V24 vocal -> V25 drafts -> V26 grants -> V27 links -> V28 client grant expiry** upgrade on a restored copy of the real production schema and verify every historical row/table fingerprint using the existing release controller and migration policy. Confirm `main` has not acquired later migration numbers; if it has, re-evaluate the plan.

## Separate synthetic staging cutover (requires a later explicit approval)

1. Freeze evidence hashes, snapshot and back up the existing staging MySQL volume and any synthetic accounts, tasks, grants, linked identities and related Keycloak state. Do not expose secrets or data in CI logs.
2. Keep the old stage and OAuth setup running on its prior known-good backend image. Do not promote the new backend or change the existing database URL yet.
3. On a separately named, empty staging schema or volume with **separate credentials**, run the corrected migrations V1–V28 and validate the migration policy and all relevant production-vocal/MCP tables, including the V28 grant-expiry schema change. The new schema is additional; **do not replace** the existing `matrix_prp_mcp_stage` schema or its volume in place.
4. If continuity of the existing synthetic users/grants is required, devise and test a **table-by-table, FK-safe data transfer** into the new schema, with referential-integrity checks, identity-link and Keycloak realm consistency, schema/row counts and cryptographic fingerprints. Use a disposable restored copy first. Do not import `flyway_schema_history` from the old stage.
5. Complete real PKCE, two-user scope isolation, read-only MCP calls and immediate PRP authorization-revocation regression on the new schema. Ensure the MCP write flag remains false.
6. Only then, with a separate approval and rollback, switch the **test-only** backend database connection to the new schema and rebuild the test backend in a controlled window. Keep the old schema/volume and prior image for rollback until explicit sign-off.
7. Recheck the production PRP process, production schema version, root DNS/Nginx, and actual resource usage before and after. Never touch production service, production database or public ingress during this task.

Preserve the existing V24–V26 staging history and Stage 1–3 acceptance artifacts as valid historical evidence of their original code revision. This new branch has no authority to rewrite them. A green disposable CI run does **not** prove the stateful staging cutover.

## Read-only host observation (2026-10-25)

The existing staging deployment was measured by its operator: `prp-mcp-stage-backend-1` uses `/root/matrix-prp-mcp-staging/app/deploy/mcp-staging/compose.yaml` plus `app/deploy/mcp-oauth-stage/backend-overlay.yaml`, its image was created on 2026-10-21, and its private MySQL schema `matrix_prp_mcp_stage` reports successful legacy `V24 mcp write drafts`, `V25 mcp client grants`, `V26 mcp identity links`. The installed JAR SHA256 is `d2cefed386154d30188327a48e31f63c5e9999def135deac0d0374fabe773db2`. This is an operator-supplied snapshot rather than independently attested server evidence. It reinforces the explicit stop gate; preserve the old stage image and schema. Production `matrix-prp.service` was reported `active`. No migration, Nginx, Docker or database change was executed to produce these facts.

## Verification commands (source/CI only)

```bash
node app/scripts/verify-db-migrations.mjs
node --test app/scripts/migration-policy-contract.test.mjs
python3 -m unittest discover -s app/deploy -p 'test_migration_policy.py'
# Full GitHub disposable MySQL integration must also pass, then staging upgrade needs separate approval.
```

Merge blockers stay active: branch `main` reconciliation, CI, reviewed production restore and data preservation, and the stage cutover above. No merge/deployment permission is implied by this document.
