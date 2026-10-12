CREATE TABLE IF NOT EXISTS prp_records (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  module_code VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  record_date DATE NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_prp_records_user_created (user_id, created_at),
  INDEX idx_prp_records_module_date (module_code, record_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_tasks (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  module_code VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  priority VARCHAR(32) NOT NULL DEFAULT 'medium',
  status VARCHAR(32) NOT NULL DEFAULT 'todo',
  due_date DATE NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_prp_tasks_user_status_due (user_id, status, due_date),
  INDEX idx_prp_tasks_priority_due (priority, due_date),
  INDEX idx_prp_tasks_module_created (module_code, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_finance_transactions (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  type VARCHAR(32) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  category VARCHAR(128) NOT NULL,
  account VARCHAR(128) NOT NULL DEFAULT 'default',
  merchant VARCHAR(255) NOT NULL DEFAULT '',
  note TEXT NOT NULL,
  transaction_date DATE NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_prp_finance_user_date (user_id, transaction_date),
  INDEX idx_prp_finance_type_date (type, transaction_date),
  INDEX idx_prp_finance_category_date (category, transaction_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_finance_accounts (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  name VARCHAR(128) NOT NULL,
  type VARCHAR(64) NOT NULL DEFAULT 'cash',
  currency VARCHAR(16) NOT NULL DEFAULT 'CNY',
  opening_balance DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  note VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_finance_accounts_user_name_deleted (user_id, name, deleted),
  INDEX idx_prp_finance_accounts_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_finance_categories (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  name VARCHAR(128) NOT NULL,
  type VARCHAR(32) NOT NULL,
  color VARCHAR(32) NOT NULL DEFAULT '#2563eb',
  note VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_finance_categories_user_name_type_deleted (user_id, name, type, deleted),
  INDEX idx_prp_finance_categories_user_type (user_id, type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_reviews (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  review_type VARCHAR(32) NOT NULL,
  module_code VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  summary TEXT NOT NULL,
  highlights TEXT NOT NULL,
  problems TEXT NOT NULL,
  next_actions TEXT NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_prp_reviews_user_period (user_id, period_start, period_end),
  INDEX idx_prp_reviews_type_module (review_type, module_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_tags (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL DEFAULT 1,
  name VARCHAR(128) NOT NULL,
  color VARCHAR(32) NOT NULL DEFAULT '#1d4ed8',
  description VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  deleted TINYINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_tags_user_name_deleted (user_id, name, deleted),
  INDEX idx_prp_tags_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_record_tags (
  id BIGINT NOT NULL AUTO_INCREMENT,
  record_id BIGINT NOT NULL,
  tag_id BIGINT NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_prp_record_tags_record_tag (record_id, tag_id),
  INDEX idx_prp_record_tags_tag (tag_id),
  CONSTRAINT fk_prp_record_tags_record FOREIGN KEY (record_id) REFERENCES prp_records(id) ON DELETE CASCADE,
  CONSTRAINT fk_prp_record_tags_tag FOREIGN KEY (tag_id) REFERENCES prp_tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
