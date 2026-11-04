WITH expected AS (
SELECT '8' AS version, 'V8__ai_orchestrator.sql' AS script, -1258301575 AS checksum, 2 AS installed_rank
UNION ALL
SELECT '9' AS version, 'V9__ai_provider_settings.sql' AS script, -381071370 AS checksum, 3 AS installed_rank
UNION ALL
SELECT '10' AS version, 'V10__openclaw_agent_tasks.sql' AS script, 1073854983 AS checksum, 4 AS installed_rank
UNION ALL
SELECT '11' AS version, 'V11__codex_review_jobs.sql' AS script, -667194552 AS checksum, 5 AS installed_rank
UNION ALL
SELECT '12' AS version, 'V12__repair_legacy_food_seed_encoding.sql' AS script, 80902462 AS checksum, 6 AS installed_rank
UNION ALL
SELECT '13' AS version, 'V13__finance_ledger_foundation.sql' AS script, 756462581 AS checksum, 7 AS installed_rank
UNION ALL
SELECT '14' AS version, 'V14__ai_read_tools_and_navigation_cards.sql' AS script, -794622852 AS checksum, 8 AS installed_rank
UNION ALL
SELECT '15' AS version, 'V15__wellness_common_food_reference.sql' AS script, 78438916 AS checksum, 9 AS installed_rank
UNION ALL
SELECT '16' AS version, 'V16__wellness_ai_write_drafts.sql' AS script, -189775160 AS checksum, 10 AS installed_rank
UNION ALL
SELECT '17' AS version, 'V17__wellness_personal_dish_templates.sql' AS script, 1965791850 AS checksum, 11 AS installed_rank
UNION ALL
SELECT '18' AS version, 'V18__ai_conversation_management.sql' AS script, -1809725515 AS checksum, 12 AS installed_rank
UNION ALL
SELECT '19' AS version, 'V19__ai_action_record_targets.sql' AS script, -1394431753 AS checksum, 13 AS installed_rank
UNION ALL
SELECT '20' AS version, 'V20__vocal_training.sql' AS script, 436761636 AS checksum, 14 AS installed_rank
UNION ALL
SELECT '21' AS version, 'V21__finance_bill_import.sql' AS script, 189089143 AS checksum, 15 AS installed_rank
UNION ALL
SELECT '22' AS version, 'V22__http_request_activity_audit.sql' AS script, -246937771 AS checksum, 16 AS installed_rank
UNION ALL
SELECT '23' AS version, 'V23__ai_model_invocation_telemetry.sql' AS script, -1232852341 AS checksum, 17 AS installed_rank
UNION ALL
SELECT '24' AS version, 'V24__vocal_song_library_and_assignments.sql' AS script, 1600373818 AS checksum, 18 AS installed_rank
)
SELECT
  IF(DATABASE() = 'matrix_prp', 'YES', 'NO') AS schema_match,
  COUNT(*) AS history_rows,
  SUM(CASE
    WHEN h.installed_rank=1 AND h.version='7' AND h.type='BASELINE'
      AND h.script='<< Flyway Baseline >>' AND h.checksum IS NULL AND h.success=1
    THEN 1 ELSE 0 END) AS baseline_rows_matched,
  SUM(CASE WHEN h.type='SQL' THEN 1 ELSE 0 END) AS observed_sql_rows,
  SUM(CASE
    WHEN h.type='SQL' AND e.version IS NOT NULL
      AND h.installed_rank=e.installed_rank
      AND h.script=e.script AND h.checksum=e.checksum AND h.success=1
    THEN 1 ELSE 0 END) AS source_sql_rows_matched,
  CASE WHEN DATABASE()='matrix_prp'
     AND COUNT(*)=18
     AND SUM(CASE
       WHEN h.installed_rank=1 AND h.version='7' AND h.type='BASELINE'
         AND h.script='<< Flyway Baseline >>' AND h.checksum IS NULL AND h.success=1
       THEN 1 ELSE 0 END)=1
     AND SUM(CASE WHEN h.type='SQL' THEN 1 ELSE 0 END)=17
     AND SUM(CASE
       WHEN h.type='SQL' AND e.version IS NOT NULL
         AND h.installed_rank=e.installed_rank
         AND h.script=e.script AND h.checksum=e.checksum AND h.success=1
       THEN 1 ELSE 0 END)=17
    THEN 'SOURCE_CRC_MATCH_REVIEW_ONLY'
    ELSE 'BLOCKED_OR_UNVERIFIED' END AS decision,
  'NO' AS deployment_permitted
FROM flyway_schema_history AS h
LEFT JOIN expected AS e ON h.version=e.version;
