-- REVIEW-ONLY fixed database metadata SELECT for possible production
-- PRP MySQL consistency plan. NOT a dump, lock, install or approval.
-- Run only against the verified matrix_prp schema with an authorized
-- existing metadata/SELECT account. Read NO PRP user or task table rows.
-- INFORMATION_SCHEMA object visibility is privilege-dependent:
-- counts do NOT independently prove all views/triggers/routines/events
-- are visible or that binary logs/GTIDs are backed up.
WITH object_summary AS (
  SELECT
    COALESCE(SUM(CASE WHEN TABLE_TYPE='BASE TABLE' THEN 1 ELSE 0 END),0)
      AS base_tables_visible,
    COALESCE(SUM(CASE WHEN TABLE_TYPE='BASE TABLE' AND ENGINE='InnoDB'
      THEN 1 ELSE 0 END),0) AS innodb_tables_visible,
    COALESCE(SUM(CASE WHEN TABLE_TYPE='BASE TABLE'
      AND (ENGINE IS NULL OR ENGINE <> 'InnoDB')
      THEN 1 ELSE 0 END),0) AS non_innodb_or_unknown_tables_visible,
    COALESCE(SUM(CASE WHEN TABLE_TYPE='VIEW' THEN 1 ELSE 0 END),0)
      AS views_visible
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA='matrix_prp'
), other_objects AS (
  SELECT
    (SELECT COUNT(*) FROM information_schema.TRIGGERS
      WHERE TRIGGER_SCHEMA='matrix_prp') AS triggers_visible,
    (SELECT COUNT(*) FROM information_schema.ROUTINES
      WHERE ROUTINE_SCHEMA='matrix_prp') AS routines_visible,
    (SELECT COUNT(*) FROM information_schema.EVENTS
      WHERE EVENT_SCHEMA='matrix_prp') AS events_visible
)
SELECT
  IF(DATABASE()='matrix_prp','YES','NO') AS schema_match,
  base_tables_visible,
  innodb_tables_visible,
  non_innodb_or_unknown_tables_visible,
  views_visible,
  triggers_visible,
  routines_visible,
  events_visible,
  IF(@@GLOBAL.log_bin=1,'ON','OFF') AS server_binary_logging,
  @@GLOBAL.gtid_mode AS server_gtid_mode,
  (SELECT COUNT(*) FROM flyway_schema_history) AS flyway_history_rows,
  CASE WHEN DATABASE()='matrix_prp'
        AND base_tables_visible>0
        AND innodb_tables_visible=base_tables_visible
        AND non_innodb_or_unknown_tables_visible=0
        AND (SELECT COUNT(*) FROM flyway_schema_history)=18
  THEN 'VISIBLE_BASE_TABLE_ENGINES_INNODB_REVIEW_ONLY'
  ELSE 'BLOCKED_OR_UNVERIFIED' END AS decision,
  'NO' AS backup_approved,
  'NO' AS deployment_permitted
FROM object_summary CROSS JOIN other_objects;
