-- V15: additive, idempotent common-food reference expansion.
-- These values are APPROXIMATIONS, not claims from USDA or branded nutrition labels.
-- Dry/raw/cooked preparation matters; recipes, oil and portion sizes vary.
-- Original V7 seeds remain untouched and take precedence.
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '燕麦片','raw',389,16.9,66.3,6.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='燕麦片' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '小米','raw',358,9.0,73,3.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='小米' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '大米','raw',346,7.4,77.9,0.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='大米' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '糙米','raw',370,7.5,77.2,2.7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='糙米' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '白粥','cooked',46,1,10,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='白粥' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '小米粥','cooked',48,1.4,9.5,0.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='小米粥' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '杂粮饭','cooked',118,3,24,1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='杂粮饭' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '糯米饭','cooked',135,2.6,30,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='糯米饭' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '米粉','cooked',110,1.8,24,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='米粉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '面条','cooked',109,3.8,21.7,0.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='面条' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '荞麦面','cooked',99,5,19.9,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='荞麦面' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '乌冬面','cooked',105,2.6,21.5,0.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='乌冬面' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '意大利面','cooked',158,5.8,30.9,0.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='意大利面' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '白馒头','cooked',223,7,47,1.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='白馒头' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '花卷','cooked',215,6.4,44.5,1.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='花卷' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '全麦面包','unspecified',247,13,41,4.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='全麦面包' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '吐司面包','unspecified',266,8.8,49.4,3.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='吐司面包' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '法棍','unspecified',270,9.4,56,1.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='法棍' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '红薯','cooked',86,1.6,20.1,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='红薯' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '玉米','cooked',96,3.4,21,1.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='玉米' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '南瓜','cooked',26,1,6.5,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='南瓜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '芋头','cooked',112,1.5,26.5,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='芋头' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '山药','cooked',57,1.9,12.4,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='山药' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '紫薯','cooked',86,1.6,20.1,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='紫薯' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡蛋白','cooked',52,10.9,0.7,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡蛋白' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡蛋黄','cooked',322,15.9,3.6,26.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡蛋黄' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸭蛋','cooked',185,12.8,1.5,13.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸭蛋' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鹌鹑蛋','cooked',158,13.1,0.4,11.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鹌鹑蛋' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '瘦猪肉','cooked',173,27,0,7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='瘦猪肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '猪里脊','raw',143,21.4,0,5.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='猪里脊' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '猪五花肉','raw',518,9.3,0,53,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='猪五花肉' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '猪肝','cooked',165,26,3.8,4.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='猪肝' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '猪蹄','cooked',260,21.7,0,19.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='猪蹄' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡腿肉','cooked',209,26,0,10.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡腿肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡翅','cooked',203,30.5,0,8.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡翅' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸡胸肉','raw',120,22.5,0,2.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸡胸肉' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '去皮鸡胸肉','cooked',165,31,0,3.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='去皮鸡胸肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鸭胸肉','cooked',201,29,0,8.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鸭胸肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '牛里脊','cooked',205,28,0,9.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='牛里脊' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '牛腱肉','cooked',180,29,0,6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='牛腱肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '肥牛卷','raw',330,15,0,30,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='肥牛卷' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '羊腿肉','cooked',206,28,0,9.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='羊腿肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '牛肉丸','cooked',190,15,10,10,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='牛肉丸' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '虾仁','cooked',99,24,0.2,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='虾仁' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '基围虾','cooked',99,24,0.2,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='基围虾' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鳕鱼','cooked',105,23,0,0.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鳕鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '三文鱼','cooked',206,22,0,12,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='三文鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鲫鱼','cooked',128,22,0,4.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鲫鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鲈鱼','cooked',124,24,0,2.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鲈鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '金枪鱼','cooked',132,28,0,1.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='金枪鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鱿鱼','cooked',92,15.6,3,1.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鱿鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '花甲','cooked',91,14.7,3.6,1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='花甲' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '扇贝','cooked',111,20.5,5.4,0.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='扇贝' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '北豆腐','unspecified',81,8.1,1.9,4.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='北豆腐' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '南豆腐','unspecified',56,5.2,2.5,2.7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='南豆腐' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '内酯豆腐','unspecified',50,5,2,2.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='内酯豆腐' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '豆腐干','unspecified',140,16.2,4.1,6.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='豆腐干' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '豆腐皮','unspecified',203,20,6,11,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='豆腐皮' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '豆浆无糖','unspecified',33,3.2,1.8,1.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='豆浆无糖' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '黄豆','raw',446,36.5,30.2,19.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='黄豆' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '毛豆','cooked',121,11.9,8.9,5.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='毛豆' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '红豆','raw',329,19.9,62.9,0.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='红豆' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '绿豆','raw',347,23.9,62.6,1.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='绿豆' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '鹰嘴豆','cooked',164,8.9,27.4,2.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='鹰嘴豆' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '纯牛奶全脂','unspecified',62,3.2,4.8,3.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='纯牛奶全脂' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '纯牛奶脱脂','unspecified',35,3.4,5,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='纯牛奶脱脂' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '希腊酸奶无糖','unspecified',97,9,3.6,5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='希腊酸奶无糖' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '普通原味酸奶','unspecified',85,3.6,11,3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='普通原味酸奶' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '无糖酸奶','unspecified',63,4.5,5,2.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='无糖酸奶' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '低脂奶酪','unspecified',210,26,3,11,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='低脂奶酪' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '切达奶酪','unspecified',403,25,1.3,33,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='切达奶酪' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '香蕉','raw',89,1.1,22.8,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='香蕉' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '苹果','raw',52,0.3,13.8,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='苹果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '梨','raw',57,0.4,15.2,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='梨' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '橙子','raw',47,0.9,11.8,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='橙子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '橘子','raw',53,0.8,13.3,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='橘子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '柚子','raw',42,0.8,10.7,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='柚子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '草莓','raw',32,0.7,7.7,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='草莓' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '蓝莓','raw',57,0.7,14.5,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='蓝莓' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '葡萄','raw',69,0.7,18.1,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='葡萄' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '西瓜','raw',30,0.6,7.6,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='西瓜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '哈密瓜','raw',34,0.8,8.2,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='哈密瓜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '菠萝','raw',50,0.5,13.1,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='菠萝' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '芒果','raw',60,0.8,15,0.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='芒果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '猕猴桃','raw',61,1.1,14.7,0.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='猕猴桃' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '火龙果','raw',57,1.1,13,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='火龙果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '桃子','raw',39,0.9,9.5,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='桃子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '车厘子','raw',63,1.1,16,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='车厘子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '牛油果','raw',160,2,8.5,14.7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='牛油果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '生菜','raw',15,1.4,2.9,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='生菜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '菠菜','cooked',23,3,3.8,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='菠菜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '空心菜','cooked',19,2.6,3.1,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='空心菜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '油麦菜','raw',16,1.4,2.5,0.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='油麦菜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '上海青','cooked',13,1.5,2.2,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='上海青' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '卷心菜','raw',25,1.3,5.8,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='卷心菜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '大白菜','raw',17,1.2,3.2,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='大白菜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '白萝卜','raw',18,0.7,4.1,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='白萝卜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '胡萝卜','raw',41,0.9,9.6,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='胡萝卜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '番茄','raw',18,0.9,3.9,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='番茄' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '茄子','raw',25,1,5.9,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='茄子' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '西葫芦','raw',17,1.2,3.1,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='西葫芦' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '冬瓜','cooked',13,0.4,3,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='冬瓜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '丝瓜','cooked',20,1.2,4.4,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='丝瓜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '苦瓜','raw',17,1,3.7,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='苦瓜' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '彩椒','raw',31,1,6,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='彩椒' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '洋葱','raw',40,1.1,9.3,0.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='洋葱' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '香菇','cooked',34,2.2,6.8,0.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='香菇' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '平菇','cooked',33,3.3,6.1,0.4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='平菇' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '金针菇','cooked',37,2.7,7.8,0.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='金针菇' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '木耳泡发','cooked',25,1.5,6,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='木耳泡发' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '海带','cooked',43,1.7,9.6,0.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='海带' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '紫菜干','raw',300,30,50,3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='紫菜干' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '花生米','raw',567,25.8,16.1,49.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='花生米' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '核桃仁','raw',654,15.2,13.7,65.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='核桃仁' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '杏仁','raw',579,21.2,21.6,49.9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='杏仁' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '腰果','raw',553,18.2,30.2,43.8,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='腰果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '开心果','raw',562,20.2,27.2,45.3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='开心果' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '黑芝麻','raw',573,17.7,23.4,49.7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='黑芝麻' AND preparation='raw');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '橄榄油','unspecified',884,0,0,100,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='橄榄油' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '菜籽油','unspecified',884,0,0,100,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='菜籽油' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '花生油','unspecified',884,0,0,100,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='花生油' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '黄油','unspecified',717,0.9,0.1,81.1,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='黄油' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '白砂糖','unspecified',387,0,100,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='白砂糖' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '蜂蜜','unspecified',304,0.3,82.4,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='蜂蜜' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '黑巧克力','unspecified',598,7.8,45.9,42.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='黑巧克力' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '方便面干面饼','unspecified',460,9,61,20,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='方便面干面饼' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '饺子猪肉白菜','cooked',220,8,27,9,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='饺子猪肉白菜' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '馄饨清汤','cooked',105,6,14,3,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='馄饨清汤' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '包子猪肉','cooked',225,9,31,7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='包子猪肉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '煮玉米','cooked',96,3.4,21,1.5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='煮玉米' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '炒米粉','cooked',188,4,29,6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='炒米粉' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '白米饭炒饭','cooked',185,6,27,6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='白米饭炒饭' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '番茄炒蛋','cooked',110,6.5,5,7,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='番茄炒蛋' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '清蒸鱼','cooked',125,22,1,4,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='清蒸鱼' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '清炒西兰花','cooked',80,3,7,5,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='清炒西兰花' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '水煮鸡胸','cooked',165,31,0,3.6,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='水煮鸡胸' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '烤红薯','cooked',90,1.6,21,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='烤红薯' AND preparation='cooked');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '可乐普通','unspecified',42,0,10.6,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='可乐普通' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '无糖可乐','unspecified',0,0,0,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='无糖可乐' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '美式咖啡无糖','unspecified',2,0.1,0,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='美式咖啡无糖' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '牛奶拿铁无糖','unspecified',46,2.5,3.8,2.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='牛奶拿铁无糖' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '橙汁纯','unspecified',45,0.7,10.4,0.2,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='橙汁纯' AND preparation='unspecified');
INSERT INTO prp_wellness_foods (name,preparation,calories_100g,protein_100g,carbs_100g,fat_100g,source_note)
SELECT '啤酒普通','unspecified',43,0.5,3.6,0,'通用参考估算值，非品牌标签；按每100g可食部'
WHERE NOT EXISTS (SELECT 1 FROM prp_wellness_foods WHERE owner_user_id IS NULL AND name='啤酒普通' AND preparation='unspecified');