# Matrix PRP 功能目录（自动生成）

> 由 `app/config/feature-registry.json` 生成。运行 `node app/scripts/sync-features.mjs` 更新，请勿手工编辑。
> 已实现仅表示代码进入 main，不等于生产环境或 iPhone 实机验收完成。AI 聊天由独立 Shell 路由管理。

## 已实现的功能

| 编码 | 名称 | Web 入口 | Mobile 入口 | 权限范围 | 后端模块 |
| --- | --- | --- | --- | --- | --- |
| `dashboard` | 首页概览 | `/` | `pages/home/index` | 登录用户 | `dashboard` |
| `records` | 记录管理 | `/records` | `pages/record/index` | 登录用户 | `records` |
| `tasks` | 任务计划 | `/tasks` | `pages/task/index` | 登录用户 | `tasks` |
| `finance` | 财务管理 | `/finance` | `pages/finance/index` | 登录用户 | `finance` |
| `wellness` | 健康中心 | `/wellness` | `—` | 登录用户 | `wellness` |
| `reviews` | 复盘中心 | `/reviews` | `—` | 登录用户 | `reviews` |
| `tags` | 标签管理 | `/tags` | `—` | 登录用户 | `tags` |
| `knowledge` | 知识库 | `/knowledge` | `—` | 仅管理员 | `knowledge` |
| `videos` | 视频学习库 | `/videos` | `pages/video/index` | 登录用户 | `video` |
| `notifications` | 消息与提醒 | `/notifications` | `—` | 登录用户 | `notification` |
| `practice` | 智能刷题中心 | `/practice` | `—` | 登录用户 | `practice` |

## 业务资源域（部分为聚合入口，其余仅分类）

| 编码 | 名称 | 状态 | Web 入口 | 说明 |
| --- | --- | --- | --- | --- |
| `life` | 生活 | 聚合入口 | `/life` | 日常、习惯、健康和家庭事务 |
| `learning` | 学习 | 聚合入口 | `/learning` | 课程、考试、证书和成长记录 |
| `work` | 工作 | 分类 | `—` | 项目、会议、任务和职业成长 |
| `interests` | 兴趣 | 分类 | `—` | 阅读、旅行、音乐和长期爱好 |
| `social` | 社交 | 分类 | `—` | 联系人、互动和关系维护 |
| `finance` | 财务 | 分类 | `—` | 收入、支出、账单和财务复盘 |

## 使用说明

- 登录和数据隔离为基础服务；PWA、视频存储与通知投递为模块内部能力。
- Web 导航由生成的 `app/web/src/generated/features.ts` 提供功能和领域聚合页清单，路由由校验脚本核实。
- 学习、生活聚合页仅组织已有业务功能；AI 聊天使用独立 Shell 路由，不作为可安装业务模块。
- Mobile 只登记已存在的页面，没有入口不意味着该功能已在移动端实现。
- 详细维护方式参阅 `app/docs/technical/feature-registry.md`。
