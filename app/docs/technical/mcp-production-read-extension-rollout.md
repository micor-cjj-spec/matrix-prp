# PRP production wellness + read-only MCP extension — review-only

## Goal
Keep the existing **six health scopes**, health create/update/delete draft approvals and ChatGPT app approval intact, while making the 12 extra read-only tools from PRs #171, #172 and #179 available for an explicitly approved later rollout. This change does **not** deploy, modify Keycloak, increase OAuth permissions, migrate data, or remove the production publication hold.

## Explicit configuration contract
- Keep the existing production `MATRIX_PRP_MCP_PRODUCTION_WELLNESS_ONLY=true`, MCP/OAuth enabled and health write approval enabled, exactly as already approved.
- Two default-off switches must both be true for the extra reads: `MATRIX_PRP_MCP_PRODUCTION_WELLNESS_READ_EXTENSION_ENABLED=true` **and** `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED=true`. Setting just one does not grant task, record, or practice reads.
- Preserve all original six health scopes and add **exactly** `prp.tasks.read,prp.records.read,prp.practice.read` to `MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES`. The startup guard rejects missing original health scopes, extra finance or generic write scopes, incorrect issuer/resource, incorrect database and unexpected owner configuration.
- Keep the exact production resource `https://micor.top/api/mcp`, issuer `https://auth.micor.top/realms/prp-mcp-prod`, localhost `matrix_prp` MySQL, Flyway disabled and existing verified owner allowlist. The expanded MCP user list must use the **actual production owner ID**, not a staging example.
- Owner grants remain server enforced, bound to the registered `https://chatgpt.com/oauth/client.json` OAuth client. Tokens must have correct signed client ID, issuer, resource audience and new scopes. The app does not auto-grant; the owner re-authenticates with PRP password and reconsents.

## Production rollout is separately gated
1. Read-only inspect **running** production commit, runtime flags, DB, Keycloak client scope mappings, actual owner grant, discovery and retained health approval functionality. Merged main/CI alone is not deployment evidence.
2. Rehearse the exact nine-scope profile in isolation, both flags OFF and ON. Test `tools/list`, owner-only read `tools/call`, revoked scope, wrong client, and legacy health CREATE/confirm flow.
3. With separate release authorization, use the protected GitHub workflow. **Do not silently remove or bypass** `app/deploy/publication-hold.json`.
4. Grant only the three read scopes in the reviewed production Keycloak client/resource policy. Have the owner select them in PRP `/prp/me/mcp-clients` while preserving existing health rights. Reauthorize the PRP connector in ChatGPT to get a new access token.
5. Verify real signed end-to-end access and immediate revoke. Rollback just the new scope exposure and switches if required, without deleting health data or revoking unrelated rights.

## Tests
```sh
cd app/backend
./mvnw -B -Dtest=McpProductionWellnessReadExtensionTests,McpActivationGuardTests,McpWellnessAppVisibilityTests,McpOAuthToolManifestTests,McpCoreReadToolsOAuthTests,McpRecordTaskSearchOAuthTests,McpPracticeReadOAuthTests test
cd ../web
node --test scripts/mcp-scopes.test.mjs
```

**Before applying any config** independently verify the actual runtime; the presence of `MATRIX_PRP_MCP_PRODUCTION_WELLNESS_ONLY` is a precondition, not a claim that the deployment currently has it enabled.
