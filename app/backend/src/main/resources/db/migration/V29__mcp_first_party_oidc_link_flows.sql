-- Opt-in first-party PKCE account bootstrap; no existing owner mappings change.
-- Confidential verifier/nonce kept only until one-use completion or expiry.
-- These flows are for PRP-initiated Keycloak sign-in, NOT ChatGPT tokens.
CREATE TABLE prp_mcp_oidc_link_flows (
  state_hash CHAR(64) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  code_verifier VARCHAR(128) NOT NULL,
  oidc_nonce VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  consumed_at TIMESTAMP NULL,
  INDEX idx_prp_mcp_oidc_flow_owner (user_id, expires_at, consumed_at),
  CONSTRAINT fk_prp_mcp_oidc_flow_owner FOREIGN KEY (user_id)
    REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
