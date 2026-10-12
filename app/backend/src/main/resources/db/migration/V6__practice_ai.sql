-- Bounded per-user AI calls (daily quota, not a monetary spending cap).
-- Must be applied after 005-practice-center.sql.
CREATE TABLE IF NOT EXISTS prp_practice_ai_usage (
  user_id BIGINT NOT NULL,
  usage_date DATE NOT NULL,
  used_calls INT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, usage_date),
  CONSTRAINT fk_practice_ai_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
