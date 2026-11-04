# MCP structured meal drafts — Issue #152

Status: **source-only draft candidate**. This is not deployed to staging or production.
Do not enable any production MCP, OAuth or write flags as a result of this change.

## Problem

`prp_prepare_record` writes to the general personal record business table. A record
body containing text such as "620 kcal" does not create a row in
`prp_wellness_meals`/`prp_wellness_meal_items` and is intentionally invisible
to `prp_wellness_daily`. Never label such a RECORD as a saved structured meal.

## Bounded fix

Add `prp_prepare_meal` under the **existing** `prp.write.create` scope.
Parameters:
- `mealDate`: ISO calendar date, e.g. `2026-11-04`.
- `mealType`: one of `BREAKFAST`, `LUNCH`, `DINNER`, `SNACK`.
- `items`: 1–30 explicit structured food items.
  - User-approved **per-event estimate**: `{"foodId":null,"name":"chicken leg","grams":180,"calories":360.00}`. Weight may be unknown (`null`).
  - Existing accessible catalog food: `{"foodId":123,"name":null,"grams":180,"calories":null}`.
    Never invent a catalog ID or override its calculated calories.
- `note`: optional note (maximum 500 characters); describe estimation sources and
  uncertainty where applicable.

The MCP tool only calls `McpDraftService.prepare(MEAL, ...)`.
The owner must open `/prp/me/mcp-approve/{draftId}`, review the **exact**
unchangeable JSON, and re-enter their own PRP password (never in the MCP
tool or the chat). After `APPROVED`, `prp_confirm_draft` validates again
and consumes the locked row within a transaction. The resulting meal is
written with `WellnessService.addAiMeal` and `draftId` as the owner-scoped
idempotency key. Existing row locks, date/mealType slot checks, owner
isolation and duplicate confirmation replay remain intact.

Manual calories are snapshots for that eating event; unknown protein, carb
and fat totals remain **null**, not fabricated zero. The implementation
creates no nutrition catalog entries, does not reinterpret arbitrary
existing RECORD drafts and never silently migrates or duplicates a
previously reported lunch.

## Security and rollout

- No new migration; existing MCP draft kind VARCHAR(16) supports `MEAL`.
- No new OAuth scopes; `prp.write.create` and `prp.write.confirm` plus the
  server-verified owner grant are still required.
- Production flags stay disabled by default:
  `MATRIX_PRP_MCP_ENABLED=false`,
  `MATRIX_PRP_MCP_OAUTH_ENABLED=false`,
  `MATRIX_PRP_MCP_WRITE_ENABLED=false`.
- Validate against disposable MySQL and real stage with test owner data,
  including negative cases, revoked grants, replay, cross-owner denial,
  and daily calories / mealCount. Run existing full unified CI.
- Real-client stage and production acceptance are separate release decisions.
  No live customer/user meal insert is authorized by this PR.

## Acceptance matrix

1. Scope-less or read-only OAuth token cannot discover or invoke the new tool.
2. Invalid date/type, empty/overlong items, missing/negative/too-high
   manual calories or forged catalog nutrition are rejected before creating a draft.
3. Preparation stores only owner-bound draft state, not meal or food rows.
4. Foreign owner cannot read/approve/confirm this draft; password approval
   happens solely on PRP site.
5. Unapproved, rejected or expired draft cannot write a meal.
6. Approved confirmation yields one structured lunch with exactly the
   reviewed food snapshot values and updates wellness daily mealCount/calories.
7. Repeated confirmation returns original receipt without duplicate rows;
   a second independent draft for the same slot fails closed.
8. Historical generic RECORD drafts and existing meals remain unchanged.
