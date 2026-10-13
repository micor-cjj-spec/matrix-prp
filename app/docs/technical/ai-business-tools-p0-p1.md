# PRP AI Business Tools P0 + P1

## Runtime contract

- Existing JWT user identity is taken from Spring Security, propagated explicitly into the AI worker, and rechecked by current-user Business Services. The model never chooses a user ID, SQL, API endpoint, HTTP URL or Java class.
- Business reads are **disabled by default**. The user explicitly chooses application scopes via @, previews a limited summary, and confirms a single-use token. The preview is illustrative, **not an exhaustive list**: after confirmation, the model may request additional read-only records from the selected scopes for that one message, and those tool results may be transmitted to the configured upstream model. Never imply only the previewed fields leave the server.
- Scope-specific tools: tasks_list, practice_statistics, wellness_daily, wellness_trends, wellness_body_trends (separate sensitive wellness_body authorization), finance_monthly. Finance is sensitive and must be selected explicitly. Tool results cap task lists at 20 and transactions at 10 using a SQL-level LIMIT in production repositories. Monthly totals and category aggregates still require their existing complete-month computation. No notes, weight history, diagnoses, arbitrary files or unrestricted DB access.
- Navigation-only tool navigation_open is allowed without a business data grant; its output must be converted to a registered first-party relative route. Task focus links are ownership-checked. Frontend RouterLink respects the /prp/ base path and only renders allowlisted internal targets.
- Model planning uses provider-native function calling, bounded to one selection round and at most four tool calls per message. The execution layer applies the current grant independently of model instructions.
- No write operations, server commands, OpenClaw/Codex delegation or external-link launching are enabled by these changes.
- Tool metadata audit logs never store raw prompts, record descriptions or returned private data.
- Assistant navigation cards are stored separately and recovered from the existing conversation; /api/ai/conversations/{id}/messages is unchanged. New GET /api/ai/conversations/{id}/blocks is ownership-checked.

## Schema and rollout

- Flyway V14 adds prp_ai_message_blocks and prp_ai_tool_audit; it does not rewrite existing application or conversation rows.
- CI includes Maven tests, Web and Mobile builds, MySQL integration and migration/legacy-preservation verification.
- A GitHub merge is **not** a production migration. Back up and restore-test matrix_prp and other server assets before enabling V14; apply only once using the established Flyway baseline/migrate/validate process. Do not clean or repair historical migrations.
- Rollout must verify real provider tool-call support, SSE through the existing Nginx proxy, @Finance grant wording, cross-user access restrictions, navigation on iPhone PWA, and card restoration after revisiting a conversation.

## P2 explicitly out of scope

Any create/update/delete operation must introduce a separate explicit action request, input validation, before/after preview, confirmation, idempotency protection and auditing. Do not wire business writes directly to the current read-only tool registry.

## Second review regression

- Native tool observations are inserted as lower-trust user-reference data, never as system instructions. Oversized observations fail closed to a bounded warning instead of truncating JSON mid-field.
- The real-MySQL `AiDatabaseIT` exercises 20-task/10-transaction caps, verifies other tenants' titles and spending remain absent, and rejects deep links to another tenant's task ID.
- Automated CI is not a live remote-server or third-party-model smoke test. Production remains unchanged pending explicit rollout approval.

## PR #39 wellness read extensions

The read-only registry now supports `wellness_trends` for 7/14/30 days of diet calories and exercise minutes (no weight), and separately authorized `wellness_body_trends` for weight. The independent AI wellness draft endpoints explicitly require human validation and are **not** part of the read-only tool registry; they never let a tool change existing data.
