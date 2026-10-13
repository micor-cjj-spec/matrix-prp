-- Additive-only AI tool execution metadata and structured navigation cards.
-- Never change V1-V13 or existing user, finance, task and chat rows.
CREATE TABLE IF NOT EXISTS prp_ai_message_blocks (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    block_type VARCHAR(32) NOT NULL,
    module VARCHAR(40) NOT NULL,
    label VARCHAR(120) NOT NULL,
    route VARCHAR(300) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_ai_blocks_owner_message (user_id,message_id),
    CONSTRAINT fk_ai_block_message FOREIGN KEY (message_id)
        REFERENCES prp_ai_messages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_ai_tool_audit (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    conversation_id CHAR(36) NOT NULL,
    tool_name VARCHAR(80) NOT NULL,
    scope VARCHAR(40) NOT NULL,
    status VARCHAR(24) NOT NULL,
    elapsed_ms BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_ai_tool_audit_user_created (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
