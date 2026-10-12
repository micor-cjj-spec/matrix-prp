# Matrix PRP · P1 变更影响分析

## 用途

在每个 PR 中识别本次修改可能影响的功能、API 路径前缀、关联测试与维护文档，为开发人员和 Codex 提供统一的改动核对表。分析基于 Git 文件路径以及唯一功能注册表，**不是**静态调用图或运行时依赖证明。

## 数据来源

- 主数据：`app/config/feature-registry.json`，每个 `type=feature` 下的 `impact` 提供 `apiPrefixes`、`tests`、`docs`。无论是否有前端页面，都以该文件登记为准。
- 路径映射：自动识别 Java 模块包、Vue 视图、Web/Mobile API 客户端、Mobile 页面、数据迁移以及注册的测试与文档。
- 跨模块变更：认证、公共库、路由、请求封装、注册表、核心数据库结构等修改触发全模块兼容性提示。
- 未分类文件：单独列出，必须人工确认，不会默认判定无影响。

## 本地运行

运行 Node.js 22，无第三方依赖：

```bash
node --test app/scripts/feature-impact.test.mjs
node app/scripts/feature-impact.mjs --base origin/main --head HEAD --out impact-report.md --json impact-report.json
```

只分析指定文件，便于验证规则（可重复传入 `--files`）：

```bash
node app/scripts/feature-impact.mjs --files app/backend/src/main/java/com/matrix/prp/video/VideoController.java
```

脚本使用 `git diff --name-only -z --diff-filter=ACDMRT origin/main...HEAD`；三点差异使用 merge-base，`--base` 与 `--head` 均按 Git ref 原样交给 `git`（不执行 shell）；若没有完整的 Git 历史或 base ref，将显示错误并失败，而不是报告零变化。

## PR 自动报告

新增 `.github/workflows/feature-impact.yml`：在 PR 指向 `main` 时触发，Checkout 完整历史，验证映射并生成两种文件。

- `impact-report.md`：用户可阅读的风险、功能、接口前缀、测试、文档、未归类文件清单。
- `impact-report.json`：便于将来接入 Codex Worker、PR 机器人与功能中心。
- GitHub Actions 作业摘要中展示 Markdown，并将两个文件上传为 14 天有效的 Actions Artifact。
- 工作流只有 `contents: read` 权限，不在 PR 中自动发表评论，不赋予修改仓库权限。

## 新增功能时如何维护

1. 先实现真实功能并更新 P0 主注册表条目。
2. 为 feature 填写 `impact.apiPrefixes`（真实 API 根路径）、`impact.tests`（仓库内现有测试文件）、`impact.docs`（真实文档路径）。
3. 执行 `node app/scripts/sync-features.mjs`，同步后端资源、前端元数据及功能目录。
4. 执行 `node --test app/scripts/feature-impact.test.mjs` 和 `node app/scripts/sync-features.mjs --check`。
5. 提交 PR 后审阅报告的未归类文件、权限风险和建议回归，不要仅凭报告将功能判定为安全。

## 边界

- API 根路径属于候选范围，不提供完整的 Controller 方法或调用图；跨模块服务调用可能未被文件路径分析发现。
- Git 路径变更不是精确的语义变更（例如 DTO 字段影响移动端）；尤其修改 `auth`、数据迁移、公共代码时仍须人工审查。
- 工具不会自动运行报告内所有建议测试；现有后端、Web、Mobile 与 MySQL CI 仍分别负责执行。
- 无法识别的新目录需要继续完善模块归属或自动匹配规则，不能假装不存在。
