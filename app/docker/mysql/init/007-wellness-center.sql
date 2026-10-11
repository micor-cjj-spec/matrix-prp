-- Apply manually to EXISTING matrix_prp after a verified backup.
-- The Docker init directory only runs when a brand-new MySQL volume is created.
-- This migration is intentionally numbered 007 to avoid in-flight AI/practice migrations.
CREATE TABLE IF NOT EXISTS prp_wellness_profiles (
 user_id BIGINT NOT NULL PRIMARY KEY,
 height_cm DECIMAL(5,1) NULL,
 timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_wellness_profile_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_foods (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 owner_user_id BIGINT NULL,
 name VARCHAR(120) NOT NULL,
 preparation VARCHAR(32) NOT NULL DEFAULT 'unspecified',
 calories_100g DECIMAL(9,2) NOT NULL,
 protein_100g DECIMAL(9,2) NOT NULL DEFAULT 0,
 carbs_100g DECIMAL(9,2) NOT NULL DEFAULT 0,
 fat_100g DECIMAL(9,2) NOT NULL DEFAULT 0,
 source_note VARCHAR(255) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY idx_wellness_food_owner (owner_user_id, name),
 CONSTRAINT fk_wellness_food_user FOREIGN KEY (owner_user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_meals (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 meal_date DATE NOT NULL,
 meal_type VARCHAR(16) NOT NULL,
 note VARCHAR(500) NULL,
 idempotency_key VARCHAR(80) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_wellness_meal_user_day (user_id, meal_date),
 UNIQUE KEY uk_wellness_meal_idempotency (user_id, idempotency_key),
 CONSTRAINT fk_wellness_meal_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_meal_items (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 meal_id BIGINT NOT NULL,
 food_id BIGINT NULL,
 food_name VARCHAR(120) NOT NULL,
 grams DECIMAL(9,2) NOT NULL,
 calories DECIMAL(10,2) NOT NULL,
 protein_g DECIMAL(10,2) NOT NULL,
 carbs_g DECIMAL(10,2) NOT NULL,
 fat_g DECIMAL(10,2) NOT NULL,
 is_estimate TINYINT(1) NOT NULL DEFAULT 0,
 INDEX idx_wellness_item_meal (meal_id),
 CONSTRAINT fk_wellness_item_meal FOREIGN KEY (meal_id) REFERENCES prp_wellness_meals(id) ON DELETE CASCADE,
 CONSTRAINT fk_wellness_item_food FOREIGN KEY (food_id) REFERENCES prp_wellness_foods(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_exercises (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 performed_on DATE NOT NULL,
 name VARCHAR(100) NOT NULL,
 duration_minutes INT NOT NULL,
 estimated_kcal DECIMAL(9,2) NULL,
 note VARCHAR(500) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_wellness_exercise_user_day (user_id, performed_on),
 CONSTRAINT fk_wellness_exercise_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_body_metrics (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 measured_on DATE NOT NULL,
 weight_kg DECIMAL(6,2) NOT NULL,
 body_fat_pct DECIMAL(5,2) NULL,
 waist_cm DECIMAL(6,2) NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_wellness_metric_user_day (user_id, measured_on),
 CONSTRAINT fk_wellness_metric_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS prp_wellness_goals (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id BIGINT NOT NULL,
 effective_from DATE NOT NULL,
 daily_calories DECIMAL(8,2) NOT NULL,
 daily_protein_g DECIMAL(8,2) NULL,
 weekly_activity_minutes INT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uk_wellness_goal_user_effective (user_id, effective_from),
 CONSTRAINT fk_wellness_goal_user FOREIGN KEY (user_id) REFERENCES prp_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Approximate starter values: editable reference values, not verified branded nutrition labels.
INSERT INTO prp_wellness_foods
(name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '米饭','cooked',116,2.6,25.9,0.3,'示例参考值，请核对实际食物'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='米饭' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡蛋','cooked',144,13.3,2.8,8.8,'示例参考值，按可食部重量计算'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡蛋' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡胸肉','cooked',165,31,0,3.6,'示例参考值，未包含烹调油'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡胸肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '黄瓜','raw',15,0.7,3.6,0.1,'示例参考值'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='黄瓜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '土豆','cooked',87,1.9,20.1,0.1,'示例参考值，无额外油脂'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='土豆' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '西兰花','cooked',35,2.4,7.2,0.4,'示例参考值，无额外油脂'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='西兰花' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '纯牛奶','unspecified',62,3.2,4.8,3.4,'示例参考值，品牌以包装为准'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='纯牛奶');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '香蕉','raw',89,1.1,22.8,0.3,'示例参考值'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='香蕉' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '食用油','unspecified',884,0,0,100,'示例参考值'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='食用油');
