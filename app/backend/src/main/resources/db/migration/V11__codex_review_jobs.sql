-- Additive P4 approval/audit records; does NOT run code or change existing tables.
CREATE TABLE prp_ai_codex_jobs (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  repository VARCHAR(120) NOT NULL,
  task_type VARCHAR(24) NOT NULL,
  prompt TEXT NOT NULL,
  status VARCHAR(24) NOT NULL,
  error_code VARCHAR(40) NULL,
  approved_by BIGINT NULL,
  approved_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_ai_codex_owner_recent (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
