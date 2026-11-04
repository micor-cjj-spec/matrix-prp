-- V25: owner-controlled OAuth client grants. Never stores bearer tokens or passwords.
CREATE TABLE prp_mcp_client_grants (
  user_id BIGINT NOT NULL,
  client_id VARCHAR(128) NOT NULL,
  scopes VARCHAR(512) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, client_id),
  CONSTRAINT fk_prp_mcp_client_grant_user FOREIGN KEY (user_id)
    REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
