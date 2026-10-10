# Matrix PRP — 视频学习库 MVP

> 分支 `feat/video-library-mvp`，PR #4。先完成代码与 MySQL 集成测试，再部署；**不代表已经部署到你的服务器**。

## 已完成的功能

- 视频课程目录：多级目录、创建、重命名、删除空目录。
- MP4 文件：按当前认证用户隔离，支持 Web 8 MiB 分片上传；上传中断后可重新选择**同一个文件**重试（24 小时内）。
- 视频播放器：HTML5 MP4 播放、拖动、全屏、速率 0.75～2 倍；Web 可调音量。iOS Safari 音量由实体音量键控制。
- 观看进度：登录用户维度保存；15 秒、暂停或离开时提交；返回课程重新开始时续播。
- 访问保护：后端在每次播放、更新、删除或上传时核实用户归属；仅经授权的接口能生成两小时有效的签名播放 URL。HTTP Range 支持单段 `206 Partial Content`。
- Web 登录后进入左侧“视频学习库”；uni-app H5 登录后从“今日”进入“视频学习库”，手机端第一版侧重**观看**，视频上传使用 Web。

## 建库与升级

备份数据库后执行 `app/docker/mysql/init/003-video-library.sql`；已有数据卷**不会自动再次执行** init 脚本。首次安装需要依次执行 001、002、003。可以在已配置 `mysql` 客户端的机器使用：

```bash
mysql -h 127.0.0.1 -u matrix_prp -p matrix_prp < app/docker/mysql/init/003-video-library.sql
```

不要重复创建管理员、不要清空已有卷、不要在 `test` Profile 启动真实服务器。

## 文件存储配置

```bash
sudo install -d -m 750 -o matrixprp -g matrixprp /srv/matrix-prp/video
```

示例假定存在专用的 `matrixprp` Linux 账号，按实际服务账号修改所有者。

通过后端服务管理器注入环境变量：

```text
MATRIX_PRP_VIDEO_ROOT=/srv/matrix-prp/video
MATRIX_PRP_DB_PASSWORD=<实际数据库密码>
MATRIX_PRP_JWT_SECRET=<至少32字节高熵随机值>
```

继续保留之前的 `MATRIX_PRP_BOOTSTRAP_USERNAME`、`MATRIX_PRP_BOOTSTRAP_PASSWORD` 首次创建管理员配置。**不要把密钥或数据库密码提交至仓库，也不要将 `/srv/matrix-prp/video` 配到 Nginx `root` 或 `alias` 下。**

MVP 内置单视频大小上限 2 GiB，单用户已完成文件总量上限 20 GiB；这些是应用侧限制，不替代磁盘配额、并发限流或空间监控。

## Nginx 反向代理关键设置

示例片段（整站 HTTPS 证书及域名配置需依据你的真实部署填写）：

```nginx
# 置于现有 HTTPS server { } 内
location ^~ /api/video/media/ {
    access_log off; # MVP 防止签名播放 ticket 被记入 URL 日志；生产可改脱敏日志
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering off;
    proxy_read_timeout 300s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location /api/ {
    client_max_body_size 10m; # 必须超过单个 8 MiB 上传分片
    proxy_pass http://127.0.0.1:8080;
    proxy_read_timeout 180s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location / {
    try_files $uri $uri/ /index.html;
}
```

**必须通过 HTTPS 发布**；不要暴露 MySQL 3306 或 Spring Boot 8080 到公网。请根据真实服务用户、DNS、证书及 Web/H5 托管路径合并进现有 Nginx 配置，不要盲目覆盖线上配置。

## 操作路径

1. 电脑 Web 登录 -> 左侧“视频学习库”。
2. 点“新建”创建课程，如“软考系统架构设计师”；选中该课程后再建“第 1 章”等子目录。
3. 选中目录，点“上传 MP4 视频”，等待每个分片上传完成。上传结束出现在列表。
4. 选中视频开始播放，使用 HTML5 播放控件和独立倍速下拉框。
5. 用同一账号打开手机 H5 “今日 → 视频学习库”，可找到该视频并从上次进度继续。

## API（已登录用户，除签名媒体地址外）

| 资源 | API |
| --- | --- |
| 目录列表 / 创建 | `GET /api/video/folders`、`POST /api/video/folders` |
| 目录重命名 / 删空目录 | `PUT /api/video/folders/{id}`、`DELETE /api/video/folders/{id}` |
| 视频列表 / 编辑 / 删除 | `GET /api/video/items`、`PUT /api/video/items/{id}`、`DELETE /api/video/items/{id}` |
| 上传会话 | `POST /api/video/uploads`，body `{ "folderId": 1, "title": "01.mp4", "sizeBytes": 123456 }` |
| 分片 | `PUT /api/video/uploads/{uploadId}/parts/{partNo}`，body 原始二进制，`Content-Type: application/octet-stream`，编号从 0 起 |
| 组装完成 | `POST /api/video/uploads/{uploadId}/complete` |
| 授权播放 | `GET /api/video/items/{id}/playback`，返回短期播放 URL |
| 播放进度 | `PUT /api/video/items/{id}/progress`，body `{ "positionSeconds": 12, "durationSeconds": 100 }` |

## MVP 边界 / 上线前必须验证

- 先使用真实 MySQL、1 个 100 MB 以上 MP4 以及 iPhone Safari 进行端到端上传、播放、全屏、倍速、进度与权限回归。
- MP4 内部编码必须是 Safari 支持的组合，建议 H.264/AAC；当前只检查容器基本 `ftyp` 标记，**没有 FFmpeg 转码和时长探测**。
- 签名 URL 两小时后失效，超长视频播放可能需要重新打开获得新 URL。此类 URL 仍是短时访问凭据，不要分享或放进日志/第三方统计。
- 分片会话会在 24 小时后过期，但目前还没有**定时清理过期分片**，需要运维监控和后续后台清理。
- 多实例同时完成一个上传的幂等与存储一致性、并发超额配额控制、异常事务回滚后的孤儿文件清理尚需加固。目前推荐**单实例后端 + 本地磁盘**进行内测。
- 暂无手机端上传、批量移动视频、课程封面、字幕、转码、多清晰度 HLS、真正的离线缓存。均为后续迭代内容。
- 生产环境应启用网关上传/登录限流、磁盘容量告警、文件备份及恢复演练。
