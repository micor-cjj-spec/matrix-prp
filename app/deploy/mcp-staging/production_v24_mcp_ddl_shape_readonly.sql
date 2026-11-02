-- OPERATOR REVIEW ONLY: fixed SELECT of schema metadata, never a migration.
-- Run solely in independently verified matrix_prp using existing authorized
-- SELECT/metadata access. No user rows, task rows, OAuth values or secrets.
-- This does NOT validate V1-V7 baseline DDL as a whole, verify backups or
-- authorize V25-V28, G0/B2, Keycloak, Nginx or application deployment.
WITH facts AS (
 SELECT
  (SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME = 'prp_users'
      AND TABLE_TYPE = 'BASE TABLE'
      AND ENGINE = 'InnoDB') AS owner_table_innodb,
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME = 'prp_users'
      AND COLUMN_NAME = 'id'
      AND DATA_TYPE = 'bigint'
      AND COLUMN_TYPE NOT LIKE '%unsigned%'
      AND IS_NULLABLE = 'NO') AS owner_signed_bigint_id,
  (SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME = 'prp_users'
      AND CONSTRAINT_NAME = 'PRIMARY'
      AND COLUMN_NAME = 'id') AS owner_id_primary_member,
  (SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME = 'prp_users'
      AND CONSTRAINT_NAME = 'PRIMARY') AS owner_primary_columns,
  (SELECT COUNT(*) FROM information_schema.PARTITIONS
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME = 'prp_users'
      AND PARTITION_NAME IS NOT NULL) AS owner_partition_count,
  (SELECT COUNT(*) FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'matrix_prp'
      AND TABLE_NAME IN (
       'prp_mcp_write_drafts',
       'prp_mcp_client_grants',
       'prp_mcp_identity_links',
       'prp_mcp_link_tickets',
       'prp_mcp_pairing_grant_leases'
      )) AS proposed_table_name_collisions,
  (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = 'matrix_prp'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
      AND LOWER(CONSTRAINT_NAME) IN (
       'fk_prp_mcp_draft_user',
       'fk_prp_mcp_client_grant_user',
       'fk_prp_mcp_identity_user',
       'fk_prp_mcp_link_ticket_user',
       'fk_mcp_pairing_grant'
      )) AS proposed_fk_name_collisions,
  (SELECT COUNT(*) FROM flyway_schema_history) AS history_rows,
  (SELECT COUNT(*) FROM flyway_schema_history WHERE success = 1) AS successful_history_rows,
  (SELECT COUNT(*) FROM flyway_schema_history
    WHERE version IN ('25','26','27','28')) AS proposed_version_history_rows
)
SELECT
 IF(DATABASE() = 'matrix_prp','YES','NO') AS schema_match,
 owner_table_innodb,
 owner_signed_bigint_id,
 owner_id_primary_member,
 owner_primary_columns,
 owner_partition_count,
 proposed_table_name_collisions,
 proposed_fk_name_collisions,
 history_rows,
 successful_history_rows,
 proposed_version_history_rows,
 CASE WHEN DATABASE() = 'matrix_prp'
   AND owner_table_innodb = 1
   AND owner_signed_bigint_id = 1
   AND owner_id_primary_member = 1
   AND owner_primary_columns = 1
   AND owner_partition_count = 0
   AND proposed_table_name_collisions = 0
   AND proposed_fk_name_collisions = 0
   AND history_rows = 18
   AND successful_history_rows = 18
   AND proposed_version_history_rows = 0
  THEN 'V25_V28_FK_DDL_SHAPE_MATCH_REVIEW_ONLY'
  ELSE 'BLOCKED_OR_UNVERIFIED' END AS decision,
 'NO' AS deployment_permitted
FROM facts;
