-- Run this migration manually on EXISTING MySQL volumes before launching the new backend.
-- MySQL /docker-entrypoint-initdb.d only runs for brand-new volumes.
CREATE TABLE IF NOT EXISTS prp_users (
  id BIGINT NOT NULL AUTO_INCREMENT,
  username VARCHAR(32) NOT NULL,
  display_name VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_admin TINYINT NOT NULL DEFAULT 0,
  enabled TINYINT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_invitations (
  id BIGINT NOT NULL AUTO_INCREMENT,
  code_hash CHAR(64) NOT NULL,
  issuer_user_id BIGINT NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  used_at DATETIME(6) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_invitation_hash (code_hash),
  CONSTRAINT fk_prp_invitation_issuer FOREIGN KEY (issuer_user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
