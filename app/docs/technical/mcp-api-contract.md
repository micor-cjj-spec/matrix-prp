# REST API → MCP contract policy (Phase 1)

This project keeps the **existing** Spring Boot REST API, stateless MCP transport, OAuth, owner-scoped authorization and approval-gated drafts. This phase does not register any new tools, update Keycloak, modify the database or deploy to production.

## Files

- `app/config/mcp-api-baseline.json`: frozen inventory of the 216 REST routes observed on `main` at `58dac6d0` (33 `@RestController` classes). This is an incremental compatibility baseline, **not** an assertion of MCP coverage.
- `app/config/mcp-capabilities.json`: explicitly reviewed `mapped`, `partial` and `excluded` decisions.
- `app/scripts/mcp-api-contract.mjs`: source-level inventory, manifest validation, scope/registered-tool checking and markdown/JSON reports.
- `app/scripts/mcp-api-contract.test.mjs`: regression tests for detection, blocking, exemptions and stale mappings.
- `.github/workflows/feature-impact.yml`: enforces the contract on pull requests targeting `main` and uploads a report artifact.

## Development policy

1. Add or change a business capability in the existing Service layer. REST and MCP adapters must call the same business service; do not duplicate business rules.
2. Every **new REST route** must be registered in `mcp-capabilities.json` with:
   - `status: "mapped"`, a real `@McpTool` name registered by `McpToolConfiguration`, its OAuth scope, and at least one test path whose source exercises the named tool; **or**
   - `status: "excluded"` and a substantive, security/transport/product-specific reason. Explicit exclusions are meant for internal authentication, approval, binary streaming and similar endpoints, not a generic bypass for business features.
3. A new route may not declare `partial`. Do not claim a REST business operation is fully represented by an MCP tool when filters, completeness, side effects, or response semantics differ. Route-to-tool mappings may be many-to-one (for example, the wellness draft tools) when they expose equivalent business capabilities.
4. For write tools, retain authenticated owner identity, independently checked OAuth scope and owner grant, immutable preview, separate human approval, exactly-once commit and cross-user isolation. The model never supplies its own user ID or approval verdict.
5. Add or extend an MCP tool-call test. Exercise success and at least one refusal/authorization edge case. Do not treat a syntactic manifest entry as proof of behavior.
6. Confirm the `Feature Impact Report / impact-report` check passes before merge. Repository branch protection must separately make this check **required** to enforce merging; this PR does not change repository settings.
7. Enable new production scopes and tools only in a **separate** reviewed release, after OAuth consent, grant isolation, client regression and rollback checks. In particular, `McpProductionWellnessGuard` currently pins the production health-only scope set.

Existing routes absent from the contract file are reported as `legacy-gap`; these 148 routes are a known backlog, not an automatic CI failure. Existing `partial` routes remain reported separately. Newly introduced routes must receive a full MCP mapping or a justified exclusion.

## Running locally

```bash
node --test app/scripts/mcp-api-contract.test.mjs
node app/scripts/mcp-api-contract.mjs --out mcp-api-report.md --json mcp-api-report.json
```

The report lists exact routes and statuses by feature. `mapped` means the registered tool covers the intended business operation in **source code**, not that the tool is actually advertised, consented to or callable by ChatGPT in a particular production environment. Production exposure depends on runtime OAuth scopes, activation flags, owner/client grants and deployment policy.

## Legacy route removals

Removing or renaming a previously frozen route makes CI fail with `Stale frozen route`. Review the REST breaking change and deliberately remove the exact old route from `mcp-api-baseline.json` and any corresponding classification. Do **not** append new routes to the legacy baseline: this would allow missing MCP coverage to be misrepresented as historical debt.

## Constraints

The parser reads `@RestController` method mappings such as `@GetMapping`, `@PostMapping` and explicit `@RequestMapping(method=RequestMethod.GET)` in Java source. It is a conservative static preflight, not a live Spring MVC handler map, and cannot prove Spring profile-specific runtime registration. Unsupported or nonliteral routes must be accompanied by a dedicated runtime contract test; do not silently weaken the scanner for new syntax. A later phase should compare this source inventory to a Spring `RequestMappingHandlerMapping` export to catch dynamically registered routes.

## Follow-up priorities

Phase 2: fill core read gaps for health food/templates/goals/trends, task filters/summary, records and practice; then video progress and reviews. Phase 3: introduce module-scoped writes and production expansion only after independent security validation. The gap report is the work queue, not authorization to expose every existing REST API.