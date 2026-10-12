# Matrix PRP — Nginx /prp/ 子路径部署与 iPhone 推送

## 生产环境
- Web 由 Nginx 托管 /var/www/prp，公网 URL 以 /prp/ 开头。
- 后端 Java 21 经 matrix-prp.service 在 127.0.0.1:11000 提供 /api/**。
- 数据库为 Docker matrix-mysql 内独立 matrix_prp，不跟随本次前端更新。
- 仅发布前端无需重启 Java systemd 服务、无需执行数据库迁移，也不应改动视频存储。

## 变更原因
旧版 Vite 默认 base=/、Vue Router 从 / 启动、Service Worker 注册 /sw.js、PWA Manifest 默认启动 /。
子路径部署容易让应用资源、Service Worker 作用域、通知点击跳转与 /prp/ 不一致。

本次新增配置：构建时设置 VITE_APP_BASE=/prp/；本地开发默认 /。
Manifest 使用相对于 Manifest 本身的 id/start_url/scope/icon 路径。
Service Worker 的注册、退出解绑和通知点击跳转均遵循相同应用 scope。
后端 API 继续使用 /api；切勿自动改为 /prp/api。

## Nginx 配置检查
先使用 `sudo nginx -T` **在服务器本地**检查已有配置；下面只是参考片段。
只调整已有 HTTPS server 块中的相关 location，勿将整段重复粘贴造成冲突。

~~~nginx
location = /prp { return 301 /prp/; }

location = /prp/sw.js {
    alias /var/www/prp/sw.js;
    add_header Cache-Control "no-cache, no-store, must-revalidate" always;
}

location ^~ /prp/ {
    alias /var/www/prp/;
    try_files $uri $uri/ /prp/index.html;
}

location ^~ /api/ {
    proxy_pass http://127.0.0.1:11000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
~~~

说明：假设后端 API 是 /api/**，因此 proxy_pass 末尾不要加斜杠，否则可能剥离 /api 前缀。
Nginx 如已有其他 API 路由，保留并按需合并，勿影响服务器其它服务。

## 前端构建
在已部署源码的 Git 仓库根目录执行：

~~~bash
git fetch origin
git switch main
git pull --ff-only origin main
cd app/web
npm ci
VITE_APP_BASE=/prp/ npm run build
node scripts/verify-deploy-base.mjs /prp/
~~~

如代码仍在 PR 分支，请先合并后发布；本说明不会自动更新实际服务器。

## 发布到 /var/www/prp
先检查目录用途，确保它只存放 PRP 前端构建产物，不包含用户上传或持久化数据。
~~~bash
sudo cp -a /var/www/prp "/var/www/prp.backup.$(date +%Y%m%d-%H%M%S)"
sudo rsync -a --delete dist/ /var/www/prp/
sudo nginx -t
sudo systemctl reload nginx
~~~
仅静态前端更新时无需 `systemctl restart matrix-prp`，不要操作 matrix-mysql 或其数据卷。
如需回滚，将备份目录内的静态产物恢复到 /var/www/prp 后重新加载 Nginx。

## 验证
1. `curl -I https://你的域名/prp/`：200 且返回 HTML。
2. `curl -I https://你的域名/prp/sw.js`：200、JavaScript 内容，不应是 index.html。
3. `curl -I https://你的域名/prp/manifest.webmanifest`：200，body 包含相对 start_url/scope。
4. 浏览器网络面板中 `/prp/assets/` JS/CSS 均为 200，避免 HTML 回退导致 MIME 错误。
5. `curl -i http://127.0.0.1:11000/api/health`：应正常响应；公网 /api 应由 Nginx 保留前缀转发。
6. iPhone Safari 加入主屏幕并从桌面图标打开，进入“消息与提醒 → 推送设备”订阅，然后测试通知。
7. 若旧 PWA 图标仍启动 / 而不是 /prp/，则在确认无未同步本地数据后移除旧图标并重新安装。修改 Manifest id 可能被视为新应用安装。

如出现 VAPID 错误，请确认 systemd 服务中的 VAPID 公私钥成对设置；勿公开私钥。
如出现 HTTP 400，检查后端的 Push endpoint 白名单和入参校验；AbortError 优先排查推送服务可达性。
