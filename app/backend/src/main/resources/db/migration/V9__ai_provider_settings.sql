-- P1 additive migration. V1-V8 must not be modified or replayed on existing databases.
CREATE TABLE prp_ai_provider_credentials (
  user_id BIGINT NOT NULL,
  provider_id VARCHAR(24) NOT NULL,
  encrypted_api_key VARCHAR(2048) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY (user_id, provider_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE prp_ai_preferences (
  user_id BIGINT NOT NULL PRIMARY KEY,
  provider_id VARCHAR(24) NOT NULL,
  model_id VARCHAR(100) NOT NULL,
  updated_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
