-- Additive-only vocal library and lesson tracking.
-- Existing recordings remain unchanged; take associations are stored separately.
CREATE TABLE prp_vocal_songs (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  title VARCHAR(120) NOT NULL,
  artist VARCHAR(120) NOT NULL DEFAULT '',
  original_key VARCHAR(20) NOT NULL DEFAULT '',
  status VARCHAR(16) NOT NULL DEFAULT 'LEARNING',
  note VARCHAR(500) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_vocal_songs_owner_status (user_id, status, updated_at, id),
  CONSTRAINT fk_vocal_songs_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_vocal_song_sections (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  song_id BIGINT NOT NULL,
  title VARCHAR(120) NOT NULL,
  start_marker VARCHAR(40) NOT NULL DEFAULT '',
  end_marker VARCHAR(40) NOT NULL DEFAULT '',
  focus VARCHAR(500) NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_vocal_sections_owner_song_order (user_id, song_id, sort_order, id),
  CONSTRAINT fk_vocal_sections_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE,
  CONSTRAINT fk_vocal_sections_song FOREIGN KEY (song_id) REFERENCES prp_vocal_songs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_vocal_lessons (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  lesson_date DATE NOT NULL,
  teacher_name VARCHAR(120) NOT NULL DEFAULT '',
  summary TEXT NULL,
  feedback TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_vocal_lessons_owner_date (user_id, lesson_date, id),
  CONSTRAINT fk_vocal_lessons_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_vocal_assignments (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  lesson_id BIGINT NULL,
  song_id BIGINT NULL,
  section_id BIGINT NULL,
  title VARCHAR(160) NOT NULL,
  detail TEXT NULL,
  due_date DATE NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'TODO',
  completed_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_vocal_assignments_owner_status_due (user_id, status, due_date, id),
  INDEX idx_vocal_assignments_owner_lesson (user_id, lesson_id, id),
  CONSTRAINT fk_vocal_assignments_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE,
  CONSTRAINT fk_vocal_assignments_lesson FOREIGN KEY (lesson_id) REFERENCES prp_vocal_lessons(id) ON DELETE SET NULL,
  CONSTRAINT fk_vocal_assignments_song FOREIGN KEY (song_id) REFERENCES prp_vocal_songs(id) ON DELETE SET NULL,
  CONSTRAINT fk_vocal_assignments_section FOREIGN KEY (section_id) REFERENCES prp_vocal_song_sections(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_vocal_take_links (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  take_id BIGINT NOT NULL,
  song_id BIGINT NULL,
  section_id BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_vocal_take_links_take (take_id),
  INDEX idx_vocal_take_links_owner_song_section (user_id, song_id, section_id, take_id),
  CONSTRAINT fk_vocal_take_links_user FOREIGN KEY (user_id) REFERENCES prp_users(id) ON DELETE CASCADE,
  CONSTRAINT fk_vocal_take_links_take FOREIGN KEY (take_id) REFERENCES prp_vocal_takes(id) ON DELETE CASCADE,
  CONSTRAINT fk_vocal_take_links_song FOREIGN KEY (song_id) REFERENCES prp_vocal_songs(id) ON DELETE SET NULL,
  CONSTRAINT fk_vocal_take_links_section FOREIGN KEY (section_id) REFERENCES prp_vocal_song_sections(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
