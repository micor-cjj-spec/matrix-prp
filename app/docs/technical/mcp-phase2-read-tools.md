# Phase 2: opt-in core read tools (review / no production enablement)

This phase adds **five** read-only, bounded MCP capabilities, reusing the existing REST business services. The tools are registered in the code but **hidden by default**, independently of the advertised OAuth read scopes.

| Tool | REST capability | Existing OAuth scope | Limit |
| --- | --- | --- | --- |
| `prp_tasks_summary` | `GET /api/tasks/summary` | `prp.tasks.read` | Aggregate task counts |
| `prp_wellness_trends` | `GET /api/wellness/summary/trends` | `prp.wellness.read` | 1–90 days |
| `prp_wellness_goals` | `GET /api/wellness/goals` | `prp.wellness.read` | Most recent 20 |
| `prp_wellness_frequent_foods` | `GET /api/wellness/foods/frequent` | `prp.wellness.read` | At most 12 |
| `prp_wellness_dishes` | `GET /api/wellness/dishes` | `prp.wellness.read` | First 20 personal dish templates |

## Activation boundary

- New property: `matrix-prp.mcp.additional-read-tools-enabled`; environment variable: `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED`.
- **Default is false**. The legacy task-only MCP manifest remains two tools, the existing production health manifest remains nine tools (or ten with the separately configured ChatGPT app-only approval).
- Even with the opt-in property set, tools appear only when an operator has explicitly advertised the matching existing read scope. The OAuth JWT, authenticated owner, client grant, expanded user allowlist and MCP scope filter still apply.
- All write-related flags, scopes, approval policies and runtime guards are unchanged. No Keycloak changes, DB migration, Nginx edits, API route changes or production deployment are part of this PR.
- **Do not** toggle the new production flag based solely on CI success. Release is separately gated by authentic client authorization, least-privilege grant review, real-client tools/list and tools/call tests, user boundaries and rollback readiness.

## Review and testing

```bash
cd app/backend
./mvnw -B -Dtest=McpCoreReadToolsOAuthTests,McpOAuthToolManifestTests,McpWellnessOAuthTests,McpWellnessAppVisibilityTests test
cd ../..
node --test app/scripts/mcp-api-contract.test.mjs
node app/scripts/mcp-api-contract.mjs --out mcp-api-report.md --json mcp-api-report.json
```

The API–MCP coverage report changes from **148** to **143** legacy gaps; mappings increase from 16 to 19, with partial mappings increasing from 7 to 9. A partial mapping is deliberately not treated as full parity (for example, the dish tool returns only 20 items).

If this code later proceeds to an approved canary, verify exact tools/list visibility with the flag both OFF and ON, token/owner scoping, lack of health/tool metadata expansion when OFF, and that all write-capable tools remain gated.