-- V18: additive conversation metadata without altering historical conversation rows.
-- The production deployer fingerprints complete legacy rows (SELECT *), so even
-- adding a nullable column to prp_ai_conversations breaks its preservation gate.
-- V18 was not applied to production; the failed rollout only migrated a throwaway copy.
CREATE TABLE prp_ai_conversation_meta (
  conversation_id CHAR(36) NOT NULL PRIMARY KEY,
  title_override VARCHAR(120) NULL,
  title_source VARCHAR(16) NOT NULL DEFAULT 'AUTO',
  deleted_at DATETIME(6) NULL,
  is_pinned TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_ai_conversation_meta FOREIGN KEY (conversation_id)
    REFERENCES prp_ai_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
