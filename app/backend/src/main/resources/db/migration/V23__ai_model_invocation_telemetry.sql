-- Additive-only, owner-scoped metadata log; no prompts, generated output or credentials.
-- Existing conversations, AI usage limits, and user records remain untouched.
CREATE TABLE prp_ai_invocation_log (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    provider VARCHAR(32) NOT NULL,
    model_id VARCHAR(100) NOT NULL,
    credential_source VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    failure_category VARCHAR(40),
    elapsed_ms BIGINT NOT NULL,
    first_token_ms BIGINT,
    input_tokens BIGINT,
    output_tokens BIGINT,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_ai_invocation_owner_date (user_id,created_at,id),
    INDEX idx_ai_invocation_retention (created_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
