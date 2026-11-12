# PRP MCP: ChatGPT 内完成健康记录创建确认（开发候选）

状态：**Draft / 不可直接部署生产**，2026-11-12。

## 用户目标与不可妥协条件

- 用户在 `chatgpt.com` 的聊天页面输入“早餐吃了两个鸡蛋”，ChatGPT 查询 PRP 食品库，并生成准确的健康餐食草稿。
- 用户在 **ChatGPT 当前聊天中审核并确认**；不得要求打开 PRP App / PRP 审批页。
- 不得向 ChatGPT 提供 PRP 密码、OAuth Token、一次性关联码，也不得跳过 Keycloak OAuth 的 `private_key_jwt`、PKCE S256、`iss`/`aud`/签名校验。
- 服务端必须继续依照已验证的 PRP 用户绑定、精确客户端 ID、双重 Scope（OAuth Token 与 PRP 独立授权）、当前用户、草稿超时及事务锁，验证每次写入。
- 写操作由用户明确同意；未确认时不得保存健康记录。

## 修复的两个独立问题

1. Spring AI MCP Annotation 自动生成的 `McpWellnessSupport.Input` 与 `AiMealItem` JSON Schema 把互斥字段全部列为 `required`。目录食品仅允许 `{foodId,grams}`，估算食品仅允许 `{name,calories,grams?}`，二者不应同时提供 `name/calories/foodId`。工具边界改为 `Map<String,Object>`，然后通过服务端 ObjectMapper 还原强类型 `Input` 并执行原有 `McpWellnessSupport.validate`、食品库权限及快照检查；**不接受**提供用户 ID、SQL 或任意更新指令。
2. `McpDraftService.confirm` 原本只接受 PRP 页面密码审批后的 `APPROVED` 草稿。新增默认关闭的受限路径：仅在 `matrix-prp.mcp.chatgpt-health-confirm-enabled=true` 且 OAuth 已验证用户、固定 ChatGPT CIMD 客户端、`prp.wellness.write.create` 和 `prp.wellness.write.confirm` 都已授予时，`WELLNESS_CREATE` 的 `PENDING` 草稿可以由 ChatGPT 的高风险工具确认提交。所有任务、财务、健康更新及删除仍保持原有独立审批要求。

## 应在 ChatGPT 中呈现的操作

1. 读取 `prp_wellness_foods`，选择经核实的“鸡蛋（熟）”，例如 `foodId=2`、每 100 g 144 kcal。
2. 调用 `prp_prepare_wellness_create`，参数示例：

```json
{
  "entity": "meal",
  "input": {
    "meal": {
      "mealDate": "2026-11-12",
      "mealType": "BREAKFAST",
      "note": "两个鸡蛋，按每个约50g可食部估算；无额外烹调用油",
      "items": [{"foodId": 2, "grams": 100}]
    }
  }
}
```

3. 在 ChatGPT 聊天中展示服务端回传的不可变草稿预览，明确是“两个鸡蛋、约144千卡”，由用户在 ChatGPT 对提交工具操作作出确认（建议该应用权限设为 **每次操作都询问**）。
4. 仅用户确认后调用 `prp_confirm_wellness_draft(draftId)`，凭有效 OAuth 和匹配 Scope 在事务内提交一条。随后读取同日记录以核对 ID、热量和营养信息。

## 安全边界与已知平台限制

- ChatGPT 的原生工具确认提示由宿主控制；工具的 `destructiveHint=true` 不能独立证明某位真人点击过批准。官方文档也明确：工具 annotation 并不能替代服务端鉴权与确认。**因此，默认关闭的新通道不得在尚未验证宿主弹出审批且用户真实批准之前开启生产。**
- 首期仅让低风险 `WELLNESS_CREATE` 借助宿主确认。修改、删除、财务、任务等仍按原流程。要实现“所有操作均强制在 GPT 内可验证地审批”，下一阶段需要专门的 MCP Apps 审批卡片（在 ChatGPT 内显示）与 `_meta.ui.visibility=[\"app\"]` 的控件调用，绑定不可变草稿与用户身份；不得伪造宿主确认收据。
- 即使启用 ChatGPT 权限设置“总是询问”，服务器也不应假称它收到密码二次验证或已取得可验证的人工点击凭证。需要在产品安全评审中明确此风险。
- 不修改生产 Keycloak、CIMD、Nginx、PRP MySQL 表结构、现有 Scope 和用户数据。

## 验收矩阵（至少）

- 自动生成的 `tools/list` 不再把食品 item 的 `name` 与 `calories` 误标为必填；工具能提交 `{foodId:2,grams:100}` 与 `{name:...,calories:...,grams:...}`。
- 错误输入（额外字段、目录/估算混用、不同实体、无 Scope、他人记录）全部拒绝。
- 功能开关缺省关闭时 `PENDING` 不可确认。错误客户端、缺少任一 Scope、过期草稿、修改及删除草稿均不可通过聊天路径。
- ChatGPT 对确认工具真实弹出审批；用户拒绝时健康数据不变；接受后恰好一条新餐食，重放不重复写入。
- 任何真实授权 Token、PRP 密码或审批码均不出现在 ChatGPT 文字、GitHub 测试工件、Nginx 日志。
- 真实生产切换必须在隔离 CI、真实 ChatGPT 交互验证、回滚演练后另行批准；本 Draft PR 不构成生产部署许可。
