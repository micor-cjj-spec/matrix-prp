-- V17: owner-scoped personal frequent dishes. This is NOT the verified per-100g food catalog.
-- A template is one serving ("大碗 / 17 个") with a provenance-aware energy estimate.
CREATE TABLE IF NOT EXISTS prp_wellness_dish_templates (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  merchant_name VARCHAR(100) NOT NULL DEFAULT '',
  dish_name VARCHAR(120) NOT NULL,
  portion_label VARCHAR(100) NOT NULL DEFAULT '',
  portion_count INT NULL,
  calories_per_serving DECIMAL(10,2) NOT NULL,
  source_type VARCHAR(24) NOT NULL,
  source_note VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_personal_dish_identity (user_id,merchant_name,dish_name,portion_label),
  KEY idx_personal_dish_search (user_id,dish_name,updated_at),
  CONSTRAINT fk_personal_dish_owner FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Historic catalog-derived nutrient values remain unchanged.
-- New per-event custom calorie estimates have no known macro quantities.
ALTER TABLE prp_wellness_meal_items
  MODIFY protein_g DECIMAL(10,2) NULL,
  MODIFY carbs_g DECIMAL(10,2) NULL,
  MODIFY fat_g DECIMAL(10,2) NULL;
