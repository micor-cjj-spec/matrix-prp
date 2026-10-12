# 功能注册中心 · P0

## 单一事实来源

唯一手工维护的功能定义：`app/config/feature-registry.json`。它列举 main 分支已实现的 Web 业务入口及资源域分类。不要在 ModuleService 或 AppLayout 再编写第二套模块列表。

- `type=feature`：已进入 main 的用户功能；`status=implemented` 不表示已完成线上/设备验收。
- `type=domain`：业务资源分类，没有独立页面。保留原有 `finance` 等分类编码以兼容已有 API。
- `visibility=admin`：仅管理员可看到对应菜单；后端仍必须独立校验权限，不能只靠前端隐藏。
- `webRoute` 必须对应 Web 路由；`mobileRoute` 非空时必须对应 uni-app `pages.json`；`backendPackage` 必须存在。
- 尚在 PR 中的 AI 功能不能提前登记为已实现；等 PR 合并再修改注册表。

## 代码消费者

1. Spring Boot ModuleService 读取类路径下由注册表生成的 `feature-registry.json`，保持原来的 `/api/modules`、`/api/modules/features`、`/api/modules/domains` 响应格式（ModuleItem 六字段）。
2. Web AppLayout.vue 导入生成的 `app/web/src/generated/features.ts`，展示名称、路径、顺序及管理权限。
3. `app/docs/features/FEATURES.md` 自动生成已实现功能目录，避免人工维护清单。
4. Web Router 与 Mobile pages.json 仍负责实际页面声明；同步脚本校验所有注册的路由可找到，而不改动 Vue 懒加载机制。

## 开发流程

1. 先搜索注册表确认新需求能否复用已有模块。
2. 为真正的新功能实现业务代码、路由与安全校验，再登记唯一编码、模块描述、路径、权限和后端包。
3. 执行 `node app/scripts/sync-features.mjs` 更新生成文件；三份生成文件必须同 PR 提交。
4. 执行 `node app/scripts/sync-features.mjs --check`；现有 Web CI 构建也会执行该校验。
5. 执行后端测试、Web 与 Mobile 构建；涉及权限时增加跨用户/非管理员回归。

## P1：自动变更影响分析

每个 feature 的 `impact.apiPrefixes`、`impact.tests`、`impact.docs` 必须指向实际 API 路径和仓库内已存在的测试、文档。`app/scripts/feature-impact.mjs` 会根据 Git diff 输出候选影响范围；PR 工作流自动生成摘要和报告附件。详见 [功能变更影响分析](feature-impact.md)。

## 范围边界

P0 保留模块化单体，不拆微服务。清单涵盖用户业务入口和业务资源域，不枚举每个按钮/API/内部子能力；身份认证、通知投递、存储、CLI 等应有各自技术文档。自动影响分析属于 P1，模块功能中心和依赖图属于 P2。
