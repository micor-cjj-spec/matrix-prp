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
2. **保留** `McpDraftService.confirm` 原有 `APPROVED` 状态硬要求，禁止从聊天直接确认 `PENDING`。新增默认关闭的 MCP Apps UI 通道（`matrix-prp.mcp.chatgpt-health-approval-ui-enabled`），仅当用户在 ChatGPT 内嵌审批卡片点击批准时，才调用声明 `_meta.ui.visibility=["app"]` 的 `prp_chatgpt_wellness_approval`，由 PRP 核对正式 ChatGPT CIMD、当前用户绑定、健康写入创建与确认权限、精确草稿类型和有效期后以事务标记 `APPROVED`。随后调用原有 `prp_confirm_wellness_draft` 写入。拒绝则写 `REJECTED`。所有任务、财务、健康修改及删除继续沿用原先的审批方式。

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

3. ChatGPT 客户端展示 MCP Apps 内嵌审批卡片 `ui://prp/wellness-approval`，显示不可变草稿预览。人点击“审批并保存”才向 **app-only** 工具 `prp_chatgpt_wellness_approval(draftId, "approve")` 发起调用；点击拒绝则标记 `REJECTED`，不调用确认。
4. 用户审批成功后，在卡片内调用标准 `prp_confirm_wellness_draft(draftId)`，确保只允许 `APPROVED` 草稿；随后读取同日记录核对营养结果。

## 安全边界与已知平台限制

- 单纯依靠 ChatGPT 的原生工具确认弹窗 **不足以向 PRP 服务端证明人工点击**，因此不允许 PENDING 直接写库。MCP Apps 通过宿主约束 app-only 工具可见性；PRP 还校验已验证的 OAuth 身份、授权快照和草稿状态。恶意、非标准 MCP 客户端可能不遵守该宿主约束，所以此方案的安全边界仍需评审，不能等同于密码或 WebAuthn 二次认证。**在实际 ChatGPT UI 验证及异常流程测试之前必须保持关闭。**
- 当前首期仅实现低风险 `WELLNESS_CREATE` 的 MCP Apps 审批卡片与 app-only 动作。修改、删除、财务、任务等仍按原流程。将来扩大操作种类时需分别评审每种数据与不可逆风险，并考虑 WebAuthn 等额外的服务端可验证认证。
- 即使启用 ChatGPT 权限设置“总是询问”，服务器也不应假称它收到密码二次验证或已取得可验证的人工点击凭证。需要在产品安全评审中明确此风险。
- 不修改生产 Keycloak、CIMD、Nginx、PRP MySQL 表结构、现有 Scope 和用户数据。

## 验收矩阵（至少）

- 自动生成的 `tools/list` 不再把食品 item 的 `name` 与 `calories` 误标为必填；工具能提交 `{foodId:2,grams:100}` 与 `{name:...,calories:...,grams:...}`。
- 错误输入（额外字段、目录/估算混用、不同实体、无 Scope、他人记录）全部拒绝。
- 功能开关缺省关闭时 `PENDING` 不可确认；开关开启时，普通 `prp_confirm_wellness_draft` 仍只能确认 `APPROVED`。错误客户端、缺少任一 Scope、过期草稿、修改及删除草稿均不可通过 UI 动作。
- ChatGPT 实际渲染审批卡片，app-only 工具对模型不可见；用户拒绝时健康数据不变；接受后草稿才从 `PENDING` 进入 `APPROVED`，之后确认恰好写入一条餐食，重放不重复写入。
- 任何真实授权 Token、PRP 密码或审批码均不出现在 ChatGPT 文字、GitHub 测试工件、Nginx 日志。
- 真实生产切换必须在隔离 CI、真实 ChatGPT 交互验证、回滚演练后另行批准；本 Draft PR 不构成生产部署许可。
