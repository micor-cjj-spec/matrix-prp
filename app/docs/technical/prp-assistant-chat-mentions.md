# PRP Assistant — 对话重设计与 @ 应用引用

## 面向用户的功能

- /chat 是 Web/PWA 沉浸式聊天屏幕，保留四入口导航；手机输入法弹出时隐藏底部导航。
- PRP 助手首页、历史会话抽屉、模型切换、安全 Markdown 子集（含代码与表格）、复制回复、SSE 流式渲染。
- 输入 @ 引用三种只读数据：tasks 任务概览、practice 刷题统计、wellness 今日健康摘要；财务等模块暂未开放查询。
- 普通聊天不请求业务数据；@ 数据在授权后只能用于当前消息。

## 两步授权 API（代替布尔 consent）

1. POST /api/ai/context/preview 传 scopes，返回已最小化摘要及随机 previewId。预览本身不是发送许可。
2. 用户查看预览并明确确认后 POST /api/ai/context/confirm 传 previewId，服务端核验身份及当前模型并返回随机 contextToken。
3. POST /api/ai/chat/stream 传 content、contextScopes、contextToken。服务端验证用户、模型、范围和有效期，并原子消费一次性凭据。旧 contextConsent:true 不能单独授权。
4. 预览与确认快照暂存单实例 Java 进程的内存里，最长有效三分钟。重启或多实例部署时须重新预览。业务数据不写入聊天消息。模型回复可能引用所分享的数据。

## 技术边界与验收

- system 角色消息始终优先于会话历史；剪裁上下文时不能移除。Claude Anthropic 请求将 system 单独作为顶层字段。
- 凭据只能由所属用户使用一次，非法、过期、切换模型或错误 scopes 均被拒绝。
- 不提供健康详情、财务、文件、服务器操作权限，不执行写入；沿用现有 OpenClaw/Codex 隔离边界。
- 对模型输出执行 HTML 转义后构造受控 Markdown 标签，不允许脚本和任意外部图片；不引入 CDN。
- 不修改数据库表及历史会话，无新增 Flyway 迁移。
- 检查 CI Spring Boot 测试、Web/PWA 构建、移动 H5、MySQL/Flyway 回归，以及 iPhone PWA 软键盘、底部安全区、消息滚动和授权流程。
- 合并仓库代码不等于部署；发布前仍须备份数据库并实际验收。

