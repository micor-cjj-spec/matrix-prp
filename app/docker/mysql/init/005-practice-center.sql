-- Matrix Practice P0: apply after a verified backup to the existing matrix_prp database.
-- Never rerun Docker init scripts by deleting an existing data volume.
CREATE TABLE IF NOT EXISTS prp_practice_subjects (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  parent_id BIGINT NULL,
  name VARCHAR(120) NOT NULL,
  description VARCHAR(500) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_practice_subject_owner (user_id, parent_id),
  CONSTRAINT fk_practice_subject_owner FOREIGN KEY (user_id) REFERENCES prp_users(id),
  CONSTRAINT fk_practice_subject_parent FOREIGN KEY (parent_id) REFERENCES prp_practice_subjects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_practice_banks (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  subject_id BIGINT NOT NULL,
  title VARCHAR(160) NOT NULL,
  description VARCHAR(500) NOT NULL DEFAULT '',
  source_name VARCHAR(255) NOT NULL DEFAULT '',
  license_note VARCHAR(255) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'draft',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_practice_bank_owner_subject (user_id, subject_id),
  CONSTRAINT fk_practice_bank_owner FOREIGN KEY (user_id) REFERENCES prp_users(id),
  CONSTRAINT fk_practice_bank_subject FOREIGN KEY (subject_id) REFERENCES prp_practice_subjects(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_practice_questions (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  bank_id BIGINT NOT NULL,
  question_type VARCHAR(20) NOT NULL,
  stem TEXT NOT NULL,
  options_json JSON NOT NULL,
  answers_json JSON NOT NULL,
  explanation TEXT NOT NULL,
  difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
  status VARCHAR(20) NOT NULL DEFAULT 'draft',
  fingerprint CHAR(64) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uk_practice_question_dedup (bank_id, fingerprint),
  INDEX idx_practice_question_owner_bank (user_id, bank_id, status),
  CONSTRAINT fk_practice_question_owner FOREIGN KEY (user_id) REFERENCES prp_users(id),
  CONSTRAINT fk_practice_question_bank FOREIGN KEY (bank_id) REFERENCES prp_practice_banks(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_practice_imports (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  bank_id BIGINT NOT NULL,
  format_name VARCHAR(16) NOT NULL,
  imported_count INT NOT NULL,
  duplicate_count INT NOT NULL,
  source_name VARCHAR(255) NOT NULL DEFAULT '',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_practice_import_owner (user_id, bank_id),
  CONSTRAINT fk_practice_import_owner FOREIGN KEY (user_id) REFERENCES prp_users(id),
  CONSTRAINT fk_practice_import_bank FOREIGN KEY (bank_id) REFERENCES prp_practice_banks(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_practice_attempts (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  question_id BIGINT NOT NULL,
  submitted_answers JSON NOT NULL,
  is_correct TINYINT NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_practice_attempt_owner_time (user_id, created_at),
  INDEX idx_practice_attempt_owner_question (user_id, question_id),
  CONSTRAINT fk_practice_attempt_owner FOREIGN KEY (user_id) REFERENCES prp_users(id),
  CONSTRAINT fk_practice_attempt_question FOREIGN KEY (question_id) REFERENCES prp_practice_questions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
