-- Independent additive migration; V20 remains reserved for draft finance import.
-- Never mutate historical records or existing tables.
CREATE TABLE prp_vocal_takes (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  exercise_code VARCHAR(40) NOT NULL,
  note VARCHAR(500) NOT NULL DEFAULT '',
  duration_seconds INT NOT NULL,
  mime_type VARCHAR(40) NOT NULL,
  storage_key VARCHAR(48) NOT NULL,
  size_bytes BIGINT NOT NULL,
  analysis_json TEXT NOT NULL,
  ai_feedback TEXT NULL,
  ai_status VARCHAR(16) NOT NULL DEFAULT 'NEW',
  ai_started_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_vocal_takes_owner_date (user_id, created_at, id),
  CONSTRAINT fk_vocal_takes_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
