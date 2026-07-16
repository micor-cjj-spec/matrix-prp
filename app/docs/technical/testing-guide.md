# Testing Guide

## 测试目标

保证核心个人数据的录入、查询、统计和展示可靠。

## 测试类型

- 后端单元和服务测试。
- 后端接口和错误响应测试。
- Web 页面构建和类型检查。
- Mobile H5 类型检查和构建。
- CLI TypeScript 构建。
- 数据库初始化和迁移验证。

## 一期重点测试流程

- 登录成功和失败。
- 新增、筛选、更新、删除记录。
- 新增、筛选、更新、删除任务。
- 新增收入/支出记录。
- 财务月度统计和分类统计。
- 标签创建、编辑、删除和记录绑定。
- 读取知识库目录、查看 Markdown 文件、搜索知识库，并验证路径越权保护。
- 复盘创建、筛选、更新和删除。

## 自动验证

仓库根目录运行：

```powershell
.\app\scripts\verify.ps1
```

该脚本会执行：

- Backend: `mvnw.cmd test`
- Web: `npm run build`
- Mobile: `npm run type-check` 和 `npm run build:h5`
- CLI: `npm run build`

## 手工验收清单

- 本地服务能按 README 启动。
- 登录后能进入 Dashboard。
- 表单校验能阻止明显错误数据。
- 列表筛选、空状态和操作入口可用。
- 后端错误能在前端友好展示。
