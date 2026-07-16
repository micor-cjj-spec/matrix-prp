# Matrix PRP Docs

这里是 Matrix PRP 应用工程的文档中心。

文档会随着产品设计、AI 沟通、开发迭代、接口设计和 Bug 排查持续增长，所以采用目录化管理，避免所有内容堆在同一个目录下。

## 目录结构

```text
docs/
  product/      产品定位、用户场景、模块规划、版本范围
  technical/    技术架构、工程设计、开发规范、测试策略
  api/          API 设计、接口草案、接口变更记录
  data/         数据模型、表设计、数据字典、迁移说明
  bugs/         Bug 记录、排查过程、修复复盘
  decisions/    产品和技术决策记录
  releases/     Changelog、版本计划、发布记录
  ai-notes/     与 AI 讨论生成的阶段性方案、草稿和分析
```

## 使用原则

- 平台定位、模块规划、阶段范围放到 `product/`。
- 架构、技术栈、开发流程、测试策略放到 `technical/`。
- 接口设计和接口变更放到 `api/`。
- 数据模型、表结构、字段说明放到 `data/`。
- Bug 复现、排查、修复记录放到 `bugs/`。
- 重要取舍沉淀到 `decisions/`，不要散落在聊天记录里。
- AI 生成但尚未正式定稿的内容，先放到 `ai-notes/`。

## 命名建议

- 稳定文档使用清晰名称，例如 `overview.md`、`phase-1.md`。
- 持续追加的记录使用日期前缀，例如 `2026-07-13-auth-design.md`。
- Bug 使用日期和简短标题，例如 `2026-07-13-login-token-expired.md`。
