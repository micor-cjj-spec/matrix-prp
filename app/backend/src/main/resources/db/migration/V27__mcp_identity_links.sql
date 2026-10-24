-- V26: proof-of-control OAuth account linking with single-use, expiring tickets.
CREATE TABLE prp_mcp_identity_links (
  issuer VARCHAR(255) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  user_id BIGINT NOT NULL,
  linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (issuer, subject),
  UNIQUE KEY uq_prp_mcp_identity_user_issuer (user_id, issuer),
  CONSTRAINT fk_prp_mcp_identity_user FOREIGN KEY (user_id)
    REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_mcp_link_tickets (
  ticket_hash CHAR(64) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  client_id VARCHAR(128) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP NULL,
  INDEX idx_prp_mcp_link_ticket_owner (user_id, expires_at, consumed_at),
  CONSTRAINT fk_prp_mcp_link_ticket_user FOREIGN KEY (user_id)
    REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
