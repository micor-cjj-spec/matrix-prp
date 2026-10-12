-- New databases run scripts 001, 002, 003 in order.
-- Existing MySQL data volumes MUST apply this file manually after a backup.
CREATE TABLE IF NOT EXISTS prp_video_folders (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  parent_id BIGINT NULL,
  name VARCHAR(160) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_video_folders_user_parent (user_id,parent_id,sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_video_assets (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  folder_id BIGINT NULL,
  title VARCHAR(255) NOT NULL,
  storage_key CHAR(36) NOT NULL,
  size_bytes BIGINT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_video_storage_key (storage_key),
  INDEX idx_video_assets_user_folder (user_id,folder_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_video_uploads (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  folder_id BIGINT NULL,
  title VARCHAR(255) NOT NULL,
  size_bytes BIGINT NOT NULL,
  part_count INT NOT NULL,
  state VARCHAR(24) NOT NULL DEFAULT 'UPLOADING',
  asset_id BIGINT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  expires_at DATETIME(6) NOT NULL,
  INDEX idx_video_uploads_user_state (user_id,state,expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_video_progress (
  user_id BIGINT NOT NULL,
  video_id BIGINT NOT NULL,
  position_seconds DOUBLE NOT NULL DEFAULT 0,
  duration_seconds DOUBLE NOT NULL DEFAULT 0,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (user_id,video_id),
  CONSTRAINT fk_video_progress_asset FOREIGN KEY (video_id) REFERENCES prp_video_assets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
