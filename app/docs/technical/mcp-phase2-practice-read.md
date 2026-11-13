# Phase 2 / Batch 3: Practice MCP read tools

This is **code for review only**, dependent on PR #172 and its parent PR #171. It adds five **read-only** tools under a new least-privilege `prp.practice.read` scope. The new scope is added to the backend metadata allowlist and first-party client grant UI enumeration, **not** to production advertised scopes, Keycloak, existing owner grants or OAuth tokens.

| Tool | REST reference | Result contract |
| --- | --- | --- |
| `prp_practice_subjects` | `GET /api/practice/subjects` | At most 50 owner-scoped subjects (bounded SQL) |
| `prp_practice_banks` | `GET /api/practice/subjects/{subjectId}/banks` | At most 30 banks for an authenticated owner's subject (bounded SQL) |
| `prp_practice_questions` | `GET /api/practice/banks/{bankId}/play` | Up to 10 **published** public practice questions, default 5 |
| `prp_practice_wrong_questions` | `GET /api/practice/wrong-questions` | Up to 10 incorrect public questions, default 5; published and owner-scoped |
| `prp_practice_statistics` | `GET /api/practice/statistics` | Aggregate attempted, correct and wrong answer counts |

## Accuracy and data protection

- Use `PracticeService` and its existing owner checks instead of creating a separate AI-specific persistence layer. `PracticeService` now has explicit SQL-limited read variants; existing REST endpoint behavior remains unchanged.
- Question views use **only** `QuestionPublic` (published bank and question) and convert into compact previews with max 800 characters for stem and max 200 for each of up to eight options. If anything is clipped the response explicitly includes `truncated=true`; users should open PRP for complete question text.
- **No answer keys, explanations, drafts, pending/unpublished questions, grading actions or AI-generated answers are exposed through these five tools.** The source-backed question bank remains the authority; do not substitute AI-generated "correct answers" without owner review or verified references.
- All read tools run `McpScopeGuard.require("prp.practice.read")`, and the OAuth transport enforces the signed issuer/audience, linked PRP identity, owner grant, exact ChatGPT client allowlist and read scope. Other users' IDs return unavailable.
- An operator must explicitly set `MATRIX_PRP_MCP_ADDITIONAL_READ_TOOLS_ENABLED=true` **and** advertise `prp.practice.read` to expose these tools. Both conditions are false in the current production config; simply merging code must not expose them.

## Verification

```sh
cd app/backend
./mvnw -B -Dtest=McpPracticeReadOAuthTests,McpPracticeReadServiceTests,McpOAuthToolManifestTests,McpRecordTaskSearchOAuthTests test
cd ../..
node --test app/scripts/mcp-api-contract.test.mjs
node app/scripts/mcp-api-contract.mjs --out mcp-api-report.md
cd app/web
node --test scripts/mcp-scopes.test.mjs
```

Required negative cases: no scope, revoked client consent, wrong client or unallowlisted owner, other user's subject/bank, invalid negative or excessive limits, unpublished questions, correct answers never exposed, and explicit content truncation. Complete CI, including production-health regression suites, is a merge prerequisite.

**Release boundary:** No changes to production Keycloak, issuer, Nginx, MySQL, Web Push, Flyway or actual OAuth grants. The repository's `main` CI can trigger `Deploy PRP`; merging this or parent PRs requires separate approval even with green CI.

## Next staged work

- Clarify verified answer provenance and question-version lifecycle before building AI grading or bulk answer ingestion; neither is part of this read-only batch.
- Add separate owner-approved write drafts for practice question import/edit/grade only after an explicit write-scope and review workflow.
- Continue remaining records/video/reviews after practice read regression and security tests pass.
