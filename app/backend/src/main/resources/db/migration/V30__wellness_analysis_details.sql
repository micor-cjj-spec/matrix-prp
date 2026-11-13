-- H2-002: empty, owner-linked enrichment tables. Existing meal rows remain unchanged.
-- Images, image hashes, Base64 and unredacted order OCR must never be persisted here.
CREATE TABLE prp_wellness_meal_analyses (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  meal_id BIGINT NOT NULL,
  version_number INT NOT NULL,
  source_type VARCHAR(24) NOT NULL,
  raw_extraction_json TEXT NOT NULL,
  analysis_json TEXT NOT NULL,
  model_key VARCHAR(100) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_wellness_analysis_version (meal_id, version_number),
  INDEX idx_wellness_analysis_created (meal_id, created_at),
  CONSTRAINT fk_wellness_analysis_meal FOREIGN KEY (meal_id)
    REFERENCES prp_wellness_meals(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prp_wellness_meal_item_nutrients (
  meal_item_id BIGINT NOT NULL PRIMARY KEY,
  quantity DECIMAL(10,2) NULL,
  quantity_unit VARCHAR(24) NULL,
  consumed_ratio DECIMAL(5,4) NULL,
  weight_min_g DECIMAL(10,2) NULL,
  weight_max_g DECIMAL(10,2) NULL,
  calories_min_kcal DECIMAL(10,2) NULL,
  calories_max_kcal DECIMAL(10,2) NULL,
  protein_g DECIMAL(10,2) NULL,
  carbs_g DECIMAL(10,2) NULL,
  fat_g DECIMAL(10,2) NULL,
  fiber_g DECIMAL(10,2) NULL,
  sugar_g DECIMAL(10,2) NULL,
  sodium_mg DECIMAL(12,2) NULL,
  source_type VARCHAR(24) NOT NULL,
  confidence_level VARCHAR(16) NOT NULL,
  estimate_note VARCHAR(300) NULL,
  CONSTRAINT fk_wellness_nutrients_item FOREIGN KEY (meal_item_id)
    REFERENCES prp_wellness_meal_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
