-- Additive task review and audit only. Neither migration nor startup executes an agent.
CREATE TABLE prp_ai_agent_tasks (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  task_type VARCHAR(24) NOT NULL,
  prompt TEXT NOT NULL,
  status VARCHAR(24) NOT NULL,
  result TEXT NULL,
  error_code VARCHAR(40) NULL,
  session_ref VARCHAR(100) NOT NULL,
  approved_by BIGINT NULL,
  approved_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX idx_ai_agent_owner_recent (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
