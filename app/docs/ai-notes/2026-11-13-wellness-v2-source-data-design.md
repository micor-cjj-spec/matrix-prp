# PRP 健康中心 V2：图片仅识别、原始提取数据与营养分析入库（设计草案）

状态：**待评审 / H2-001**。日期：2026-11-13。基线：main @ 2b8ca6097ba7a39874ef39cfda90415780df49cf。
本文件仅定义实施契约，不授权合并 main、修改生产数据库或部署。保留 app/deploy/publication-hold.json 及现有安全校验。

## 1. 产品目标和明确决策

目标：用户在 PRP Web/PWA 上传食物实拍、外卖订单截图、营养标签截图，或在 ChatGPT 中提供食物描述后，快速获得**可核对的营养草稿**，并将**去敏后的原始识别数据、分析数据和用户确认后的餐食记录**分别持久化，展示更细致的健康数据。

**决策（已确认）**：
- 图片仅用于当次 AI 识别；不持久化图片、缩略图、Base64、对象存储链接或原始图片备份。
- “原始数据”专指从图片/文本提取的食品业务数据和去敏后的 OCR 文字片段，不指图片字节。
- “分析数据”包含食物拆分、估计重量/区间、营养素来源、假设、未知项、识别版本及用户确认状态。
- 最终营养统计仅采用已确认并实际保存的餐食；识别成功、草稿准备成功不等于写入成功。
- 不因“尽量丰富”而虚构精确重量、油量、蛋白质、碳水、脂肪、微量营养素或用餐事实。
- 不开发相册、图片历史回看、图片长期存储服务；不修改生产授权和发布策略。

## 2. 现有实现：复用而非重写

- Web 入口：app/web/src/views/WellnessView.vue，已包括概览、饮食、运动、身体指标、目标、简单趋势和人工餐食编辑。
- AI 入口：app/web/src/components/wellness/WellnessAiRecorder.vue，图片 + 文字 → /api/wellness/ai/prepare → 草稿修改 → /drafts/{id}/confirm；现要求食品库匹配和克数才能确认。
- 图片处理：app/web/src/utils/mealPhoto.ts；目前小于 3 MB 的 JPG/PNG/WebP 可以直接上传，**不能认为全部图片已去除 EXIF**。
- 业务模型：WellnessModels.java；食物库已有 kcal、蛋白质、碳水、脂肪每 100g 参考值；人工估算食物仅能可靠持久化单项热量，宏量营养素常为 null。
- 服务端：WellnessService.java；有单用户身份隔离、餐食幂等键和同日同餐次防重，后者阻止一天出现两条 SNACK。
- MCP：McpWellnessSupport.java；餐食、运动、指标的结构化增删改走待审批草稿和服务端确认，不允许模型自行提交 owner/SQL。
- 数据库：prp_wellness_meals、prp_wellness_meal_items、prp_wellness_foods、prp_wellness_dish_templates、prp_wellness_ai_drafts 等须继续复用。
- 已有部署规范：AGENTS.md、app/deploy/AGENTS.md、app/docs/technical/versioned-migration-policy.md。禁止修改既有 Flyway 历史迁移。

## 3. MVP 范围 / 非目标

P0：一种统一结构化输入（单餐多食物）、外卖订单截图与实拍/包装标签识别、脱敏原始提取结果、可说明的营养估算、用户确认、独立的餐食详情、每日统计完整度、移动端布局与回归测试。

P1：一次多张图片合并分析、历史常吃菜品匹配优化、按 7/30/90 天的营养构成趋势、一天多个同类加餐的体验完善。若同日多 SNACK 已能在现有代码安全改造，可随 P0 实现，但不可绕过幂等和并发保护。

非目标：睡眠/心率设备接入、医学诊断、自动健康处方、完整本体/知识图谱、跨平台 OCR 存档、票据财务核算、自动无审批写入。

## 4. 输入、提取和可信度

统一输入源枚举：FOOD_PHOTO、ORDER_SCREENSHOT、NUTRITION_LABEL、TEXT、MIXED。不要把“外卖订单里买了两份”当成“用户吃了两份”。

每次识别输出可检验的两段结构：

- raw_extraction：原始菜品名、商家（如存在）、份数/规格、包装信息、每 100g/每份营养标签、用户原话、经脱敏的 OCR 菜品相关片段、来源类型。保留模型最初解读，不随用户修改覆盖。
- ai_analysis：归一化餐次日期与类型、候选食材、重量或范围、计算公式/依据、热量区间、宏量营养素、其他营养素（仅可靠来源时）、缺失字段、来源等级、是否估算及模型/规则版本。重新识别形成新分析版本，不覆盖上个版本。
- confirmed_meal：最终日期、餐次、各项食物、可食重量/个数/份数、用户实际吃掉比例、计算后的营养快照。真实入库回执返回 mealId、itemId 和确认状态。

营养值优先级：用户确认的包装标签/官方可靠营养表 > 有明确来源的食品库 > 可复现的配方估算 > AI 粗估。优先级并不等于精度保证；字段级 provenance 要可查询。

**未知 ≠ 0**。缺少重量不得以 0g 暗示没吃；现有旧数据 0g 只可展示“重量未知”，历史明细不得自动回填虚构克数。缺少宏量营养素时 daily summary 应显示不完整而不是当作 0 合计。热量预计值在页面标记“估算”，需要用户确认。

## 5. 最小数据模型（待开发 PR 确定精确 DDL）

原表不改定义，后续通过**仅新增空表**保存详情：

A. prp_wellness_meal_analyses（餐次级，允许同餐多个版本）：
- id、meal_id（外键）、analysis_version、source_type、raw_extraction_json、analysis_json、model_key、created_at。
- raw_extraction_json 为**去敏后的初始识别内容**，analysis_json 为结构化分析与依据。两者分别限定大小、深度和字段白名单；不允许塞图片或 Base64。
- 经关联 meal_id → prp_wellness_meals.user_id 校验所有权。仅服务端生成分析版本。历史版本只读。

B. prp_wellness_meal_item_nutrients（单项营养详情）：
- meal_item_id（主键/外键）、protein_g、carbs_g、fat_g、fiber_g、sugar_g、sodium_mg、weight_min_g、weight_max_g、calories_min_kcal、calories_max_kcal、source_type、confidence_level、estimate_note。
- 所有可选营养素允许 NULL。只保存有来源或确认依据的可计算字段；原表已有 kcal 等基础字段继续为历史兼容读写入口。
- 单项营养明细通过 meal_item_id → meal_id → meals.user_id 鉴权；meal_item 删除时清除对应明细。

确认交易中：创建原餐次/明细 → 创建分析与营养详情 → 返回完整回执；任何步骤失败回滚。更新餐次时保留已保存的历史原始识别版本，不得因编辑明细发生分析错绑。删除时遵守级联与用户隔离。不要向旧数据执行批量填充或迁移修改。

真实迁移版本应在开发时从 main 当前 Flyway 版本计算，避免预占版本；新增表必须按照 app/deploy/migration-policy.json 的 create-empty 规则及 SHA256 契约，完整通过现有备份恢复/旧行指纹/DDL 独立验证。

## 6. HTTP / MCP 数据契约

复用并扩展现有 API，避免无意义的新路由：

- POST /api/wellness/ai/prepare：FormData text + 可选 image；P1 才引入 images[]。返回既有 draftId、action、values、expiresAt，同时增加 sourceType、rawExtraction、analysis、uncertainties。旧客户端仍可读取旧字段。
- PATCH /api/wellness/ai/drafts/{draftId}：仅允许受控的日期、餐次、食物、份量、营养字段修正；拒绝未定义字段、非法单位、任意 ownerId、过大文本。
- POST /api/wellness/ai/drafts/{draftId}/confirm：在确认事务中一并保存来源/分析数据；必须支持同草稿重复请求安全回执，失败不得出现半条餐食。
- GET /api/wellness/meals/{id}/analysis：仅所有者读取原始提取（已去敏）、分析依据、确认值和版本；不存在返回 404。
- GET /api/wellness/summary/daily：保持旧字段兼容，新增 nutritionCompleteness（已知项数/总项数）、estimatedStatus、能被可靠统计的营养素；如值不完整，旧 proteinG/carbsG/fatG 仍可为 null。
- MCP 继续通过现有 prp.wellness.* scope、结构化草稿、用户审批、服务端确认。可以用现有工具传结构化结果，但 ChatGPT 附图**不自动作为文件传给 MCP**；若要在 PRP 服务端直接识图，使用已授权的 Web 上传入口，绝不假装 MCP 拿到了原图。版本扩展不改变旧工具语义。

接口字段（草案）：sourceType、mealDate、mealType、items[{name,foodId?,quantity?,unit?,grams?,consumedRatio?,calories?,proteinG?,carbsG?,fatG?,nutritionSource?,estimateReason?}]、rawExtraction、analysis。正式 API 需定义大小上限、范围与 JSON Schema，未知与缺失用 null，不能悄然替换 0。

## 7. 图片/隐私/安全边界

- 图片可在浏览器内短暂存在，用于一次识别请求；不写 MySQL、对象存储、日志、聊天消息历史或长期文件目录。
- 图片上传前统一重新编码或移除 EXIF/GPS；现有 <=3 MB 直接原文件发送的路径必须调整；接口实施必要大小、分辨率、MIME 和文件头校验。
- 外卖截图可能有收货地址、姓名、手机号、订单号、支付数据；提交前提示用户裁剪/遮盖，存储前服务端对 OCR 提取结果按白名单脱敏。不能把完整订单 OCR 原文或未经脱敏的 AI 响应持久化。
- 将图片发送第三方模型前说明传输边界；不能保证外部模型提供商永不留存，遵循用户配置与供应商实际协议。
- 限定 owner、草稿有效期、审批及幂等；内容不得形成 prompt injection 指令。对接口拒绝越权读、跨账号记录、重复确认、伪造 Model 输出。
- 即便 AI 识别成功，未点击确认也不得写入正式营养统计。

## 8. UI/UX 与可视化

优先重构已有 /wellness 页面，不做全新应用。桌面端卡片网格 + 餐次明细，手机 PWA 单列卡片 + 固定快捷录入按钮，避免横向滚动。

- 概览：已确认摄入 kcal、目标对比、宏量营养素、记录完整度、今日食物/餐次；未知数据用 “— / 数据不完整”。
- 饮食明细：菜品、数量/份量、用户实际摄入比例、kcal、蛋白质/碳水/脂肪、估算来源、AI 原始提取 vs 用户确认结果；不设图片相册。
- 趋势：7/30/90 天摄入热量/宏量营养素变化、记录覆盖、体重与运动分开图表；未记录不绘制为 0；缺少单项营养素时展示可靠累计或范围及明确不完整标记。
- 输入草稿：图片/文字 → 识别结果分组 → 用户编辑分量 → 保存确认状态；未匹配食品库时应允许审核后以单次估算事件保存，**不强制创建新的公共食品条目**。
- 不自动给出医学诊断或强制热量处方。颜色含义配文字可访问标签，组件复用 Element Plus，桌面与移动端均验收。

## 9. 验收用例（必须自动化 + 人工复核）

1. 上传外卖订单截图：从业务 OCR 提取菜名、商家、购买份数，同时脱敏姓名/手机号/地址/订单号；**不能存储原图**。
2. 订单“2份水饺”但用户只吃 1 份：确认记录 1 份；订单份数和实际食用份数可追溯。
3. 实拍只有“一碗红油抄手”但不知克重/用油：保存有说明的估算餐食，不强制填虚假精确重量；宏量营养素未知是 null。
4. 营养标签包含每100g营养、包装克数：按实际吃掉的分量换算并保留标签来源，字段单位正确。
5. 一天多次加餐：不能因为同一天已有 SNACK 而无故拒绝合法第二次加餐，同时必须防止同草稿重复写入。
6. 旧的餐次和食品库正常显示；旧数据中的 0g 与 null 不被自动转换为真实值；不执行历史 backfill。
7. AI 失败、用户放弃、过期审批、重复审批、并发提交：不会误写或重复计数；失败可恢复。
8. 页面刷新后，餐食详情、当日宏量营养素/完整度、时间序列与数据库实际保存数据一致。
9. 所有权/隐私：跨账号的分析详情、营养详情无法读取；OCR 敏感字段和图片字节不可从 DB/应用日志检索。
10. Flyway SQL 与 create-empty 契约、受保护的 CI、独立数据库演练通过；本方案本身不授权生产变更。

## 10. 并行开发边界（建议任务包）

先完成 H2-001 文档评审、DTO 和数据库/接口约定。随后每个会话独立分支与独立 PR：

- H2-002：新空表、写入事务、读取/汇总数据服务；只负责 DB/后端领域与迁移约束。
- H2-003：图片/截图/标签识别、去敏、结构化草稿与 AI 估算依据；不直接修改生产数据。
- H2-004：Web/PWA 健康页面、详情与趋势；依赖冻结的 DTO/Mock，不改数据库模型。
- H2-005：MCP 兼容扩展、完整 E2E 与回归验收；依赖 H2-002/003，保留 ChatGPT 审批。
  
禁止未经独立评审直接合并 main、关闭发布暂停或部署；多会话分工目前以 GitHub Issues/PR 人工协调为准，**不宣称尚待验收的多 GPT 自动抢单功能已上线**。

## 11. 留待设计评审确认

- P0 是否需要多图一次识别（默认 P1）；单图足以先跑通闭环。
- 分项营养覆盖率计算是按食物项还是按热量权重（建议 P0 采用项数覆盖率，简单且可解释）。
- 识别数据保留期限及用户删除后的级联规则（建议跟随餐食生命周期，允许用户删除）。
- 更准确的中文食品/外卖营养数据库来源以及许可，不能用无依据数字伪装权威。
