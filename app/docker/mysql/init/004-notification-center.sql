-- On EXISTING MySQL volumes apply manually after 001/002 (and 003 when using videos).
-- All DATETIME schedule columns are UTC; the user's IANA zone is stored per rule.
CREATE TABLE IF NOT EXISTS prp_notification_rules (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 title VARCHAR(120) NOT NULL,
 body VARCHAR(500) NOT NULL,
 category VARCHAR(32) NOT NULL DEFAULT 'CUSTOM',
 schedule_type VARCHAR(16) NOT NULL,
 timezone VARCHAR(64) NOT NULL,
 local_time VARCHAR(8) NULL,
 weekdays VARCHAR(24) NULL,
 month_day TINYINT NULL,
 once_at DATETIME(6) NULL,
 next_fire_at DATETIME(6) NULL,
 enabled TINYINT NOT NULL DEFAULT 1,
 created_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 INDEX idx_notif_rules_due (enabled,next_fire_at),
 INDEX idx_notif_rules_user (user_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_notification_messages (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 rule_id BIGINT NULL,
 scheduled_for DATETIME(6) NULL,
 title VARCHAR(120) NOT NULL,
 body VARCHAR(500) NOT NULL,
 category VARCHAR(32) NOT NULL,
 created_at DATETIME(6) NOT NULL,
 read_at DATETIME(6) NULL,
 UNIQUE KEY uk_notif_once (rule_id,scheduled_for),
 INDEX idx_notif_inbox_user (user_id,id),
 CONSTRAINT fk_notif_message_rule FOREIGN KEY (rule_id) REFERENCES prp_notification_rules(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_push_subscriptions (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 endpoint_hash CHAR(64) NOT NULL,
 endpoint VARCHAR(2048) NOT NULL,
 p256dh VARCHAR(512) NOT NULL,
 auth_secret VARCHAR(256) NOT NULL,
 device_name VARCHAR(100) NOT NULL,
 created_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 UNIQUE KEY uk_notif_endpoint_hash (endpoint_hash),
 INDEX idx_notif_sub_user (user_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_notification_deliveries (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 message_id BIGINT NOT NULL,
 subscription_id BIGINT NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
 attempts INT NOT NULL DEFAULT 0,
 next_attempt_at DATETIME(6) NOT NULL,
 updated_at DATETIME(6) NOT NULL,
 UNIQUE KEY uk_notif_delivery (message_id,subscription_id),
 INDEX idx_notif_delivery_dispatch (status,next_attempt_at),
 CONSTRAINT fk_notif_delivery_message FOREIGN KEY (message_id) REFERENCES prp_notification_messages(id) ON DELETE CASCADE,
 CONSTRAINT fk_notif_delivery_sub FOREIGN KEY (subscription_id) REFERENCES prp_push_subscriptions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

