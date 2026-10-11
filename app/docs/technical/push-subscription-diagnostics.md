# iPhone / PWA Web Push 订阅故障排查

## 变更范围

- 在推送设备页对 iOS 主屏幕运行模式做预检查，避免 Safari 标签页误用。
- 订阅按钮显示处理进度，防止重复点击。
- 区分通知授权、VAPID 公钥、Service Worker、浏览器推送订阅、后端登记五个阶段。
- 检查服务端 VAPID 公钥是否为 Base64/Base64URL 编码的 65 字节 P-256 非压缩公钥。
- 已存在的本地浏览器订阅如绑定了旧公钥，则先解除旧订阅，再用当前公钥重新创建。
- 错误页面显示失败阶段及下一步建议；控制台仅输出阶段、错误类型和 HTTP 状态，不记录 JWT、endpoint 或订阅密钥。

## iPhone 操作步骤

1. 用 Safari 通过有效 HTTPS 域名访问 Matrix PRP，选择“分享 → 添加到主屏幕”。
2. **从 iPhone 桌面图标启动应用**，登录后打开“消息与提醒 → 推送设备”。
3. 点击“开启当前设备通知”，如果出现系统弹窗则允许通知。
4. 查看页面上显示的阶段和下一步提示。成功时“已订阅设备”应有该设备。
5. 点击“发送测试通知”，检查站内消息和 iPhone 系统通知。站内消息成功不代表实际推送已投递。
6. 如果出现“浏览器推送服务订阅失败（AbortError）”，先检查手机网络、代理/VPN 与 Apple Push 服务连通性；不要直接改数据库。

## 服务端排查

- GET /sw.js：应返回 200 + JavaScript，且不应重定向到 SPA 登录页。
- GET /manifest.webmanifest：应返回 200、display=standalone，并与当前 HTTPS 同源。
- GET /api/push/vapid-public-key（需携带登录凭据）：应返回 API 包装下的非空公钥，解码长度应为 65 字节；**不要在日志或聊天中公布私钥**。
- POST /api/push/subscriptions（登录状态下由前端发起）：HTTP 400 核实 endpoint 域名校验和密钥格式；401/403 检查 JWT；404 检查反向代理；5xx 检查服务日志、MySQL 与 004-notification-center.sql 数据迁移。
- 如设备成功登记，但未收到通知：检查 MATRIX_PRP_VAPID_PUBLIC_KEY / MATRIX_PRP_VAPID_PRIVATE_KEY 是否配对、Web Push 投递记录、服务器对 Apple 推送网关的出口访问，以及系统通知/专注模式。
- 有旧的浏览器 PushSubscription 但没有服务端记录时，可直接再次点击“开启当前设备通知”，本次会补登记，不需要重复申请系统权限。

## 测试矩阵

- iPhone Safari 标签页：明确提示添加主屏幕。
- iPhone 主屏幕 PWA，通知已授权：能继续到浏览器订阅和服务端登记。
- 未配置或格式错误的 VAPID 公钥：明确显示“获取服务端 VAPID 公钥失败”。
- /sw.js 无法注册：明确显示“注册 Service Worker 失败”。
- pushManager.subscribe 抛 NotAllowedError / AbortError：显示不同指导。
- POST /api/push/subscriptions 返回 400 / 401 / 404 / 500：显示相应状态和排查方向。
- VAPID 公钥轮换：移除使用旧公钥的本地订阅并重新申请。
- 重复点击：仅进行一次订阅流程；注册成功后可发送测试通知。
- 桌面 Chrome / Edge、已订阅设备刷新、用户退出登录：进行回归测试。

注意：本次为诊断和客户端兼容性改进，并不自动修改服务器证书、VAPID 配置、数据库或推送服务端；生产环境仍需实机验证。
