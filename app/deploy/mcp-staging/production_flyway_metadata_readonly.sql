-- REVIEW-ONLY QUERY, NOT A MIGRATION OR DEPLOYMENT COMMAND.
-- Requires independently authorized SELECT-only DB access through existing
-- trusted admin process. Never paste credentials, raw dump or task data.
-- Run only within the verified production PRP schema, never default mysql DB.
-- Produces schema name and Flyway migration metadata, NO business rows.
-- The output still needs redaction/owner review before external sharing.
SELECT JSON_OBJECT(
  'schema', DATABASE(),
  'history',
  (SELECT JSON_ARRAYAGG(
     JSON_OBJECT(
       'installed_rank', installed_rank,
       'version', version,
       'script', script,
       'checksum', checksum,
       'success', IF(success = 1, 'PASS', 'FAIL')
     )
   ) FROM flyway_schema_history)
) AS flyway_metadata_review;
