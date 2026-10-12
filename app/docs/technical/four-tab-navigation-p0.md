# Matrix PRP 四入口导航（Web/PWA · P0）

## 范围

- 底部固定为首页 / 应用 / 聊天 / 我的；桌面侧边栏也使用同样的四入口信息架构。
- 首页保留原仪表盘；应用页通过 `app/web/src/generated/features.ts` 展示已启用的 feature 和真实的 landing domain。
- 模块搜索、领域过滤及常用收藏；收藏位于当前设备浏览器 localStorage，按 user ID 区分，**不跨设备同步**，不写业务数据库。
- 新模块没有分类映射时默认进入“更多工具”，不改底部 Tab 数量；若需指定分类或图标，更新 `app/web/src/utils/appCatalog.ts`。
- 知识库延续“管理员可见”；不能以隐藏卡片取代 API 权限检查。
- `/chat` 为独立入口和明确的“AI 未集成”状态，不调用 DeepSeek，也没有会话保存或发送功能。后续应单独整合当前尚未合并的 AI PR #9，不能声称已支持聊天。
- `/me` 包含个人信息、通知中心、设置导航、使用说明、关于、管理员邀请及退出登录；退出登录沿用原推送解绑逻辑。
- 未修改数据库、迁移脚本、现有 API、uni-app 原生页面或部署环境。

## 路由与兼容性

新 Shell 路由：`/`, `/apps`, `/chat`, `/me`, `/me/settings`, `/me/guide`, `/me/about`。
所有旧业务入口（例如 `/learning`、`/life`、`/finance`、`/wellness`、`/videos`、`/practice`）继续保留原路径和登录保护。
在这些业务页面中，底部“应用”保持选中；`/notifications` 归属“我的”。后台无响应也不应阻止导航页面渲染。

`app/scripts/sync-features.mjs` 对上述系统 Shell 路由做独立白名单处理，其余业务路由仍必须经过功能注册表校验。
**不要**在功能注册表内编造“已实现 AI”或没有实际后端包的功能。

## 验证

1. `cd app/web && npm ci && npm run build`（包含功能注册表一致性、导航回归测试和 Vue/TypeScript 构建）。
2. `cd app/backend && ./mvnw -B test`。
3. `cd app/mobile && npm ci && npm run type-check && npm run build:h5`。
4. GitHub Actions 对真实 MySQL 运行视频/消息/健康/数据库迁移测试。
5. iPhone Safari/PWA 手动回归：安全区、底部固定导航、返回上一页、底部键盘遮挡、应用筛选、收藏、普通用户无法看到知识库、管理员邀请、通知入口、退出登录、`/prp/` 子路径刷新的历史路由。
6. 本次只在开发分支验证并提 PR；不修改生产 systemd/Nginx/MySQL/视频目录。生产验证及版本发布另行处理。
