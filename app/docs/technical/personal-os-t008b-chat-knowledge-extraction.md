# Personal OS T-008b — explicitly approved chat knowledge extraction (DRAFT)

Tracks [#228](https://github.com/micor-cjj-spec/matrix-prp/issues/228). **STACKED ON unmerged T-008a PR #231**, which is stacked on Personal OS V31 review-only #206. **DO NOT MERGE MAIN, DEPLOY, ENABLE LIVE OAUTH OR SEND REAL PERSONAL CHAT DATA UNTIL SECURITY/PRIVACY REVIEW AND APPROVAL.**

## Intended user journey

1. A PRP user writes an ordinary chat message as before; **no automatic extraction runs**. The optional button "提取知识候选" appears on an existing user-authored message only when the first-party frontend build has `VITE_PERSONAL_OS_CHAT_EXTRACTION=true`.
2. `POST /api/ai/personal-os/extract/preview` accepts only `{conversationId,messageId}` (not a raw transcript or an AI-provided source). It verifies the current user's ownership, exact persisted USER-role message, max 2,000 characters; returns exact message and configured provider/model **locally**. Nothing goes to a model.
3. User explicitly approves that exact message+model; `POST /confirm` creates a three-minute, one-use owner-scoped consent token. Nothing goes to model yet.
4. `POST /extract` atomically consumes token, re-checks owner/current chat/model selection and executes only **one selected user message** against the configured, metered AI model; no other conversation turns, messages, personal memory, wellness, finance, MCP tools or agent planner are added.
5. Strict server output schema: `{"candidates":[{"predicate":"DECLARES_SKILL|PREFERS|HAS_BACKGROUND","value":"...","evidenceQuote":"exact message substring"}]}` (0–5). Validates each relation, value and a verbatim substring of the original message. Extra/invalid fields, unsupported predicates, duplicate statements, fabricated quote and parse failures reject the entire output. Returns `sensitivity=RESTRICTED`, UUID request key, `saved=false`, quote and limitation for each candidate.
6. User **individually selects** candidates. The first-party UI sends only selected structured values through T-008a's `POST /api/memory/ai-candidates`, which persists as `AI_CANDIDATE/PENDING` and defaults RESTRICTED. User must open Personal OS's review queue and separately confirm, edit, reject or erase. Nothing is auto-confirmed or added to normal model retrieval.

## Activation boundary

Backend requires deliberate `matrix-prp.personal-os.chat-extraction.enabled=true` (default **false**).
Frontend requires deliberate build-time `VITE_PERSONAL_OS_CHAT_EXTRACTION=true` (default **hidden**).
**Both** are needed to expose the workflow; the controls do not grant MCP permissions, third-party ChatGPT automatic capture or first-party memory confirmation. All three new REST routes are explicitly excluded from MCP capabilities registry. No new OAuth/Keycloak scopes, DB schema, server secrets, model changes or public networking.

The model call uses the existing PRP AI gateway and quota reservation. Model consent is single-use and node-local (3 min TTL); an authorized request cannot be replayed. A model failure, stale message, switched provider or user logout requires a new explicit review. The model is instructed to treat all message content as untrusted data, and it cannot call tools or persist facts. This is **NOT** proof that all model suggestions are correct.

## Limits and known gaps (required before production)

- Only user-selected existing PRP chat text, not passive listening to ChatGPT official chats. Automatic every-turn processing is not implemented.
- No link to full raw chat stored in the assertion table; the evidence quote is displayed during review but not yet durably stored as a verifiable source. The `AI_CANDIDATE` origin flag means "intake via AI suggestion", not "model has verified the fact".
- Semantic duplicate detection, historical supersession and temporal source fidelity remain T-008c.
- End-to-end real provider latency, reverse-proxy read timeout (~45–75s in some **examples**, not confirmed production), isolation in multi-node restarts, quota audit and owner consent browser tests remain gating.
- This stack does not merge T-005/T-006; it has only V31 + T-008a dependencies. No real user personal content, tokens, private chats, production credentials or photos may be committed to GitHub.

## Required tests

- Disabled default route returns no preview/model call.
- Foreign or deleted chat, assistant-role message and unowned message IDs denied before outbound call.
- Preview/confirm never call a model; a changed provider invalidates grant.
- Wrong owner cannot consume owner grant; one-time replay rejected.
- Changed/deleted conversation denied before provider; fabricated quote, invalid schema or embedded action rejected.
- Synthetic valid extraction returns bounded RESTRICTED draft only; selecting suggestions saves PENDING, then **distinct** owner confirmation required.
- Full exact-SHA backend/JUnit, frontend TypeScript build, healthy prior MCP/wellness tests, actual owner UI browser review and independent security review before a release decision.
