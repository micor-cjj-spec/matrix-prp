# Matrix PRP Mobile

Matrix PRP 移动端应用，面向快速记录、快速记账、今日状态和轻量提醒。

## 技术栈

- uni-app
- Vue 3
- TypeScript
- Vite

## 本地开发

```powershell
npm install
npm run dev:h5
```

H5 开发服务默认通过 Vite 代理访问后端：

```text
/api -> http://localhost:8080
```

如需修改后端地址，可以复制 `.env.example` 为 `.env`，调整：

```text
VITE_API_PROXY_TARGET=http://localhost:8080
```

## 验证

```powershell
npm run type-check
npm run build:h5
```

也可以在仓库根目录运行统一验证脚本：

```powershell
.\app\scripts\verify.ps1
```

## 一期页面

- 登录：使用开发账号进入移动端。
- 今日状态：查看今日任务、逾期任务数、高优先级任务、最近记录和财务摘要。
- 快速记录：选择领域模块，录入标题、内容和记录日期。
- 快速记账：录入收入/支出、金额、分类、账户、对象和备注。

开发期默认账号：

- Username: `admin`
- Password: `matrix-prp`
