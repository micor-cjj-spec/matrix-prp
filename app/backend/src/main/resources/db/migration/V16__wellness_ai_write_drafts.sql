-- V16: one-time, per-user approved AI write drafts; images are not stored.
CREATE TABLE IF NOT EXISTS prp_wellness_ai_drafts (
 id CHAR(36) NOT NULL PRIMARY KEY,
 user_id BIGINT NOT NULL,
 action_type VARCHAR(24) NOT NULL,
 payload_json TEXT NOT NULL,
 description VARCHAR(500) NOT NULL,
 model_used VARCHAR(120) NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 expires_at TIMESTAMP NOT NULL,
 consumed_at TIMESTAMP NULL,
 INDEX idx_wellness_ai_draft_owner (user_id,status,created_at),
 CONSTRAINT fk_wellness_ai_draft_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
