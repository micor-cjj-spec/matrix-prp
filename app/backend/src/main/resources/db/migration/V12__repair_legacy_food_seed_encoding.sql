-- V12: Targeted repair for legacy UTF-8 food seed bytes imported as MySQL latin1.
-- Never rewrite the immutable V1-V7 SQL or alter private user-owned food records.
-- HEX UTF-8 literals are ASCII-only; latin1 conversion reproduces the known mojibake.
-- A full backup and production inspection are required before any manual application.
-- All statements are idempotent; existing row IDs, meal amounts and user data are retained.

-- 米饭 (116 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE7B1B3E9A5AD USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 116 AND f.protein_100g = 2.6 AND f.carbs_100g = 25.9 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE7B1B3E9A5AD USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE8AFB7E6A0B8E5AFB9E5AE9EE99985E9A39FE789A9 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 116 AND f.protein_100g = 2.6 AND f.carbs_100g = 25.9 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE7B1B3E9A5AD USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE8AFB7E6A0B8E5AFB9E5AE9EE99985E9A39FE789A9 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE7B1B3E9A5AD USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 116 AND f.protein_100g = 2.6 AND f.carbs_100g = 25.9 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE7B1B3E9A5AD USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE7B1B3E9A5AD USING latin1) USING utf8mb4) AS BINARY);

-- 鸡蛋 (144 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE9B8A1E89B8B USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 144 AND f.protein_100g = 13.3 AND f.carbs_100g = 2.8 AND f.fat_100g = 8.8 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE9B8A1E89B8B USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE68C89E58FAFE9A39FE983A8E9878DE9878FE8AEA1E7AE97 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 144 AND f.protein_100g = 13.3 AND f.carbs_100g = 2.8 AND f.fat_100g = 8.8 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9B8A1E89B8B USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE68C89E58FAFE9A39FE983A8E9878DE9878FE8AEA1E7AE97 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE9B8A1E89B8B USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 144 AND f.protein_100g = 13.3 AND f.carbs_100g = 2.8 AND f.fat_100g = 8.8 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9B8A1E89B8B USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE9B8A1E89B8B USING latin1) USING utf8mb4) AS BINARY);

-- 鸡胸肉 (165 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE9B8A1E883B8E88289 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 165 AND f.protein_100g = 31 AND f.carbs_100g = 0 AND f.fat_100g = 3.6 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE9B8A1E883B8E88289 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE69CAAE58C85E590ABE783B9E8B083E6B2B9 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 165 AND f.protein_100g = 31 AND f.carbs_100g = 0 AND f.fat_100g = 3.6 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9B8A1E883B8E88289 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE69CAAE58C85E590ABE783B9E8B083E6B2B9 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE9B8A1E883B8E88289 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 165 AND f.protein_100g = 31 AND f.carbs_100g = 0 AND f.fat_100g = 3.6 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9B8A1E883B8E88289 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE9B8A1E883B8E88289 USING latin1) USING utf8mb4) AS BINARY);

-- 黄瓜 (15 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE9BB84E7939C USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 15 AND f.protein_100g = 0.7 AND f.carbs_100g = 3.6 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE9BB84E7939C USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 15 AND f.protein_100g = 0.7 AND f.carbs_100g = 3.6 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9BB84E7939C USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE9BB84E7939C USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 15 AND f.protein_100g = 0.7 AND f.carbs_100g = 3.6 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9BB84E7939C USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE9BB84E7939C USING latin1) USING utf8mb4) AS BINARY);

-- 土豆 (87 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE59C9FE8B186 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 87 AND f.protein_100g = 1.9 AND f.carbs_100g = 20.1 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE59C9FE8B186 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 87 AND f.protein_100g = 1.9 AND f.carbs_100g = 20.1 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE59C9FE8B186 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE59C9FE8B186 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 87 AND f.protein_100g = 1.9 AND f.carbs_100g = 20.1 AND f.fat_100g = 0.1 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE59C9FE8B186 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE59C9FE8B186 USING latin1) USING utf8mb4) AS BINARY);

-- 西兰花 (35 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE8A5BFE585B0E88AB1 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 35 AND f.protein_100g = 2.4 AND f.carbs_100g = 7.2 AND f.fat_100g = 0.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE8A5BFE585B0E88AB1 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 35 AND f.protein_100g = 2.4 AND f.carbs_100g = 7.2 AND f.fat_100g = 0.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE8A5BFE585B0E88AB1 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE8A5BFE585B0E88AB1 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'cooked' AND f.calories_100g = 35 AND f.protein_100g = 2.4 AND f.carbs_100g = 7.2 AND f.fat_100g = 0.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE8A5BFE585B0E88AB1 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE8A5BFE585B0E88AB1 USING latin1) USING utf8mb4) AS BINARY);

-- 纯牛奶 (62 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE7BAAFE7899BE5A5B6 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 62 AND f.protein_100g = 3.2 AND f.carbs_100g = 4.8 AND f.fat_100g = 3.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE7BAAFE7899BE5A5B6 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE59381E7898CE4BBA5E58C85E8A385E4B8BAE58786 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 62 AND f.protein_100g = 3.2 AND f.carbs_100g = 4.8 AND f.fat_100g = 3.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE7BAAFE7899BE5A5B6 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE59381E7898CE4BBA5E58C85E8A385E4B8BAE58786 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE7BAAFE7899BE5A5B6 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 62 AND f.protein_100g = 3.2 AND f.carbs_100g = 4.8 AND f.fat_100g = 3.4 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE7BAAFE7899BE5A5B6 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE7BAAFE7899BE5A5B6 USING latin1) USING utf8mb4) AS BINARY);

-- 香蕉 (89 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE9A699E89589 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 89 AND f.protein_100g = 1.1 AND f.carbs_100g = 22.8 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE9A699E89589 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 89 AND f.protein_100g = 1.1 AND f.carbs_100g = 22.8 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9A699E89589 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE9A699E89589 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'raw' AND f.calories_100g = 89 AND f.protein_100g = 1.1 AND f.carbs_100g = 22.8 AND f.fat_100g = 0.3 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9A699E89589 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE9A699E89589 USING latin1) USING utf8mb4) AS BINARY);

-- 食用油 (884 kcal/100g)
UPDATE prp_wellness_foods AS f
SET f.name = CONVERT(0xE9A39FE794A8E6B2B9 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 884 AND f.protein_100g = 0 AND f.carbs_100g = 0 AND f.fat_100g = 100 AND CAST(f.name AS BINARY) = CAST(CONVERT(CONVERT(0xE9A39FE794A8E6B2B9 USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_foods AS f
SET f.source_note = CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 884 AND f.protein_100g = 0 AND f.carbs_100g = 0 AND f.fat_100g = 100 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9A39FE794A8E6B2B9 USING utf8mb4) AS BINARY)
  AND CAST(f.source_note AS BINARY) = CAST(CONVERT(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BC USING latin1) USING utf8mb4) AS BINARY);

UPDATE prp_wellness_meal_items AS i
JOIN prp_wellness_foods AS f ON f.id = i.food_id
SET i.food_name = CONVERT(0xE9A39FE794A8E6B2B9 USING utf8mb4)
WHERE f.owner_user_id IS NULL AND f.preparation = 'unspecified' AND f.calories_100g = 884 AND f.protein_100g = 0 AND f.carbs_100g = 0 AND f.fat_100g = 100 AND CAST(f.name AS BINARY) = CAST(CONVERT(0xE9A39FE794A8E6B2B9 USING utf8mb4) AS BINARY)
  AND CAST(i.food_name AS BINARY) = CAST(CONVERT(CONVERT(0xE9A39FE794A8E6B2B9 USING latin1) USING utf8mb4) AS BINARY);

