# Matrix Practice 通用多学科刷题中心 · 第一版

## 范围

- 登录用户可创建/改名/删除自己的学科、题库和题目；学科支持父子层级（API）。
- 题库为用户私有，不支持公开共享。题目必须审核后手动发布；发布的题库中只有已发布题目可以练习。
- Web/PWA 页面支持学科、题库、手动题目、文件导入、AI 生成、选择题练习、错题重练、正确率及 AI 解答。uni-app 独立页暂未添加。
- 单选/多选/判断支持自动判题。简答题、主观题评分、正式模拟考试、文件附件、PDF/Word 解析与第三方题库同步是下一阶段。
- AI 使用单独的固定 DeepSeek API 适配器，后续与 Matrix AI Orchestrator（目前仍为 PR #9）合并为统一 Provider。不要在浏览器放 API Key。

## 数据库迁移

1. 备份生产库 matrix_prp 并验证备份可恢复。
2. 若数据库是此前版本，确认 auth 表 prp_users 已存在。先执行 app/docker/mysql/init/005-practice-center.sql，再执行 006-practice-ai.sql。
3. 对现有 Docker MySQL 数据卷，初始化目录只会在第一次创建卷时自动执行。**部署新后端前，必须手动在当前库运行迁移，不要清空卷。**
4. 本分支不包含对生产服务器的部署、表自动升级或数据迁移操作。

注意：待合并的 AI PR #9 也准备了一份编号为 005 的独立迁移。文件名不同但部署顺序仍需人工核查；合并 PR 时应统一管理迁移版本，避免误认为 005 唯一。

后端需通过服务器环境变量设置：
- MATRIX_PRP_DEEPSEEK_API_KEY（必需，仅 AI 功能；没有时刷题及手工导入仍可正常使用）
- MATRIX_PRP_DB_PASSWORD、MATRIX_PRP_JWT_SECRET 等既有配置。

AI 每用户每日最多 20 次请求，每次最多生成 5 道选择题或判断题，请求超时 35 秒。额度不是美元花费的硬上限，生产仍应配置 DeepSeek 平台账户级预算/告警和 Nginx 用户级限流。

## 题库导入契约

JSON：数组，包含 type（single/multiple/boolean）、stem、options[{key,text}]、answers[]、explanation、difficulty（easy/medium/hard）。示例：

\`\`\`json
[
  {
    "type": "single",
    "stem": "下面哪个属于 Java 的关键字？",
    "options": [{"key":"A","text":"class"},{"key":"B","text":"function"}],
    "answers": ["A"],
    "explanation": "class 用于声明类。",
    "difficulty": "easy"
  }
]
\`\`\`

CSV：UTF-8，表头固定 type,stem,options,answers,explanation,difficulty；options 格式 A:文本|B:文本，answers 格式 A 或 A|C；支持标准 CSV 双引号转义和换行。单次最多 200 道、内容不超过 1MB。客户端先调用 /api/practice/imports/preview，再通过 /api/practice/banks/{id}/imports 导入，服务端会重新完整校验。重复内容以题库内 SHA-256 指纹去重，整个导入以事务提交，失败回滚。

导入与 AI 生成的题目 **只能先保存成草稿**，发布前请核验题目与答案。若从第三方来源导入，需自行确认版权许可；未获得转发授权的内容不要公开发布。

## API

基地址 /api/practice：
- GET/POST /subjects；PUT/DELETE /subjects/{id}
- GET /subjects/{subjectId}/banks；POST /banks；PUT/DELETE /banks/{id}；PUT /banks/{id}/status?status=published
- GET/POST /banks/{bankId}/questions；PUT/DELETE /questions/{id}；PUT /questions/{id}/status?status=published
- POST /imports/preview；POST /banks/{bankId}/imports
- GET /banks/{bankId}/play（不返回标准答案）；POST /questions/{id}/check（评分后返回答案）
- GET /statistics；GET /wrong-questions
- POST /banks/{bankId}/ai/generate；POST /questions/{id}/ai/explain

## 权限 / 安全边界

- 所有读写必须通过登录 JWT，SQL 始终校验当前 user_id；不可按请求中的 userId 授权。
- 题库与题目默认私人所有，API 不提供跨用户访问；后端必须独立鉴权而不能依赖前端隐藏菜单。
- 练习接口不返回正确答案，提交后才返回答案及参考解析；历史答题记录按用户隔离。
- 有答题历史的题目不可删除，可撤回发布，避免历史数据意外丢失。
- AI 来源题目仅用于辅助学习，可能错误；AI 讲解不等同于人工审核。
- 大型题库、题库共享、公共发布、异步任务、AI 消耗成本统计及可观测性需要后续增强。

## 验证

在仓库根目录运行 node app/scripts/sync-features.mjs --check。
后端：cd app/backend && ./mvnw -B test。
Web：cd app/web && npm ci && npm run build。
MySQL：在有真实数据库的环境按用户 A/B 分别创建学科、题库、题目和练习，测试猜测 ID 的跨用户访问、导入回滚和重复导入。
手机：通过已部署的 Web PWA /prp/ 访问（需另行验收路由基础路径适配 PR #11）。
