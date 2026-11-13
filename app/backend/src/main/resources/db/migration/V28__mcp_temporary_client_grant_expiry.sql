-- Separate create-only lease table: no ALTER/UPDATE to historical client grants.
-- Each temporary pairing grant is denied by SQL after its absolute deadline,
-- even if the browser never returns to PRP or the host has no scheduler.
CREATE TABLE prp_mcp_pairing_grant_leases (
  user_id BIGINT NOT NULL,
  client_id VARCHAR(128) NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id,client_id),
  CONSTRAINT fk_mcp_pairing_grant
    FOREIGN KEY (user_id,client_id)
    REFERENCES prp_mcp_client_grants(user_id,client_id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
