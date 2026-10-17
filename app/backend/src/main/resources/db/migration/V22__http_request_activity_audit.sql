-- Additive-only, metadata-only HTTP request log. Existing AI tool audit is V14.
CREATE TABLE prp_api_request_log (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    http_method VARCHAR(8) NOT NULL,
    route_pattern VARCHAR(200) NOT NULL,
    status_code SMALLINT NOT NULL,
    elapsed_ms BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_api_request_log_owner_date (user_id,created_at,id),
    INDEX idx_api_request_log_retention (created_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
