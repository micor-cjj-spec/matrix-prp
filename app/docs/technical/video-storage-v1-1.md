# P1-VIDEO-02 — 视频存储架构优化

## 实现概况

- 视频存储与业务解耦：`VideoStorage` 接口负责分片、组装、私有媒体存在性判断、打开读取流和删除；默认 `LocalVideoStorage` 保留旧版磁盘目录结构。**接口是后续接入对象存储的扩展点，目前还没有 S3 实现。**
- 媒体传输方式：`MATRIX_PRP_VIDEO_DELIVERY=java`（默认）保持旧版 Java HTTP Range；设置为 `nginx` 时，必须先配置受保护的 Nginx internal alias，后端只在验证签名播放票据并再次验证文件归属后返回 `X-Accel-Redirect`。
- 删除文件安排在成功数据库事务提交后执行，避免数据库回滚导致视频文件已经被删除；如果文件删除失败，保留磁盘孤儿文件，并输出日志供运维修复。
- 定时清理过期上传（最初 24 小时有效）：每次最多 100 条，默认 1 小时间隔。删除临时文件成功才删除过期上传记录；文件删除失败会保留 `EXPIRED` 状态供下次重试。
- `GET /api/video/storage/usage` 返回**当前登录用户**的视频数量、已保存的文件字节数、总上限 20 GiB。正在上传的文件仍需要实际磁盘剩余空间监控；创建新上传任务时会同时考虑有效未完成任务的预留配额。
- 无数据库变更、无需新迁移 SQL，沿用 `003-video-library.sql` 及原视频路径。

## Linux 存储目录

存储根目录建议独立于代码和镜像：

```text
/srv/matrix-prp/video/
├── media/
│   └── <用户ID>/<服务端生成的UUID>.mp4
└── temp/
    └── <用户ID>/<上传会话UUID>/<分片号>.part
```

后端环境变量：

```bash
MATRIX_PRP_VIDEO_ROOT=/srv/matrix-prp/video
MATRIX_PRP_VIDEO_DELIVERY=java  # 默认；Nginx 配置与权限验证后改为 nginx
```

在 Linux 上确保 Spring Boot 服务账号对整个存储根目录有读写权限。如果要使用 `nginx` 模式，确保 **Nginx worker 账号** 对 `media` 及下级用户目录拥有读取和穿越权限，但不需要对上传的 `temp` 目录有访问权限。可以通过专用用户组或 ACL 配置；**不要把整个存储目录 chmod 777**。如果 Spring Boot 在容器中，还要把该目录挂为稳定的宿主机卷，两边保持相同的文件权限。

## Nginx 卸载模式

在已有 HTTPS `server { }` 内合并以下关键配置，参考 `app/docker/nginx/video-storage.conf.example`：

```nginx
location ^~ /_internal_prp_video/ {
    internal;
    alias /srv/matrix-prp/video/media/;
}
location ^~ /api/video/media/ {
    access_log off;
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Nginx 路径 `/_internal_prp_video/` **绝对不能去掉 `internal;`**。只有后端成功完成权限验证后才通过内部重定向指向真实磁盘文件。Nginx 接管 MP4 Range / HEAD 响应。媒体票据在 URL 中，必须使用 HTTPS、关闭原始查询字符串的访问日志，不要将其放入第三方分析服务。

操作步骤：

1. 在测试环境先保持 `MATRIX_PRP_VIDEO_DELIVERY=java`，跑已有上传/播放回归，确认原文件路径保持不变。
2. 为 Nginx 配置上面的 `internal` 与 `alias`，检查 Nginx 进程读取文件权限。
3. `nginx -t` 通过后 reload Nginx，再把后端变量改为 `nginx` 并重启。
4. 未登录、无权限或票据错误/过期请求应为拒绝响应；直接 GET `/_internal_prp_video/...` 应当返回 **404**。
5. 在 iPhone Safari / Chrome 验证 MP4 进度拖动返回 `206 Partial Content`，并确认 Java 实例不再承担媒体文件流式输出。
6. 如果未配置 Nginx 正确内部映射，**不要启用 nginx delivery**；回滚只需恢复 `MATRIX_PRP_VIDEO_DELIVERY=java`。

原有 `GET /api/video/items/{id}/playback` 及 `/api/video/media/{id}?ticket=...` URL 不变，不要求前端重新适配。

## 自动清理与备份

每小时运行过期上传清理任务（`matrix-prp.video.cleanup-delay-ms`，默认 3600000 ms，可调整）。服务运行日志会记录无法清理的上传会话，供人工调查。

**边界**：这轮尚不自动删除数据库提交失败后形成的孤儿正式媒体文件，避免误删仍需恢复的数据；这类文件应在核对数据库和备份后清理。视频和 MySQL 需要一起备份到独立磁盘或异地位置，并定期进行恢复演练。

## 验收矩阵

- Java 单元测试验证磁盘写入、分片组装、随机键、用户目录隔离、文件删除及无效键校验。
- MySQL 8.4 集成测试验证上传和续传状态、存储用量、分段播放、过期会话清理、跨用户拒绝。
- 线上验收仍需真实 MP4、100MB+ 上传、Nginx internal 转发 / Range 以及 iPhone Safari 实机回归。

上线前必须完成磁盘空间告警、备份演练与用户上传限流。本阶段采用单实例应用，**多实例共享上传任务、并发配额与清理锁机制未实现**。
