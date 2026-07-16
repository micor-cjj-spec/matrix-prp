# Matrix PRP CLI

Matrix PRP 的命令行工具，面向快速录入、查询和自动化脚本。

## 技术栈

- Node.js
- TypeScript
- Commander
- Axios

## 本地使用

```powershell
npm install
npm run build
npx tsx src/index.ts --help
```

默认 API 地址是 `http://localhost:8080/api`，也可以通过 `MATRIX_PRP_API_BASE_URL` 或 `login --api` 覆盖。

测试或临时运行时，可以用 `MATRIX_PRP_CONFIG_DIR` 指定配置目录，避免写入默认用户目录。

## 常用命令

```powershell
npm run dev -- login -u admin -p matrix-prp
npm run dev -- health
npm run dev -- me
npm run dev -- dashboard
npm run dev -- module list --type domain

npm run dev -- tag list
npm run dev -- tag add -n phase-one -d "一期建设"
npm run dev -- tag update 5001 -n review-loop -c "#0f766e" -d "复盘闭环"
npm run dev -- tag delete 5001

npm run dev -- knowledge search README

npm run dev -- record add -m work -t "记录标题" -c "记录内容" --tag-ids 1,2
npm run dev -- record list -m work --tag-id 1 -d 2026-07-13 -q "记录"
npm run dev -- record update 1001 -m work -t "更新后的记录" -c "新的记录内容" --tag-ids 2
npm run dev -- record delete 1001

npm run dev -- task list --status todo -m work -p high --due 2026-07-13
npm run dev -- task add -m work -t "任务标题" --due 2026-07-13
npm run dev -- task update 1001 -m work -t "更新后的任务" -p high --due 2026-07-14
npm run dev -- task done 1001
npm run dev -- task status 1001 in_progress
npm run dev -- task delete 1001

npm run dev -- finance add -t expense -a 19.90 -c tools -n "开发工具"
npm run dev -- finance list --month 2026-07 -t expense -c tools
npm run dev -- finance update 3001 -t income -a 299.00 -c salary --account bank
npm run dev -- finance delete 3001
npm run dev -- finance summary --month 2026-07
npm run dev -- finance categories --month 2026-07
npm run dev -- finance account list
npm run dev -- finance account add -n cash -t cash --currency CNY --opening 0 --note "daily wallet"
npm run dev -- finance account update 7001 -n bank -t bank --currency CNY --opening 200
npm run dev -- finance account delete 7001
npm run dev -- finance category list -t expense
npm run dev -- finance category add -n tools -t expense -c "#0f766e" --note "work tools"
npm run dev -- finance category update 8001 -n salary -t income -c "#2563eb"
npm run dev -- finance category delete 8001

npm run dev -- review list --type weekly -m work --start 2026-07-01 --end 2026-07-31
npm run dev -- review add --type weekly -m work -t "本周回顾" -s "本周完成一期基础闭环"
npm run dev -- review update 4001 --type monthly -m learning -t "月度回顾" -s "更新后的复盘"
npm run dev -- review delete 4001
```

登录后 token 会保存到当前用户目录：

```text
~/.matrix-prp/cli-config.json
```
