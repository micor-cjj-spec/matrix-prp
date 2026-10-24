-- V24: additive, per-owner, one-time MCP draft confirmation. No historical data modified.
CREATE TABLE prp_mcp_write_drafts (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  kind VARCHAR(16) NOT NULL,
  payload_json TEXT NOT NULL,
  result_json TEXT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  approval_failures SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  approved_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP NULL,
  INDEX idx_prp_mcp_owner_status (user_id, status, expires_at),
  CONSTRAINT fk_prp_mcp_draft_user FOREIGN KEY (user_id)
    REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
