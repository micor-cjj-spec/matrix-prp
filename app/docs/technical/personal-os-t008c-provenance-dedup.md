# Personal OS T-008c — verifiable chat provenance and conservative knowledge evolution

Issue [#228](https://github.com/micor-cjj-spec/matrix-prp/issues/228), parent #181. This review-only change is **stacked on T-008b Draft #238 → T-008a Draft #231 → V31 review-only #206**. **DO NOT MERGE, DEPLOY, REGISTER MCP SCOPES OR ENABLE CHAT EXTRACTION WITHOUT SEPARATE APPROVAL AND CI.**

## What T-008c implements

1. **Owner-verified source pointer, no new database tables.** Existing `prp_personal_assertions.source_type/source_ref` can now store `CHAT_MESSAGE` + a numeric ID referring to an existing user-authored PRP chat message. At candidate submission, the server rejects an unpaired source ID/quote, foreign/deleted/assistant-role source, or a quotation not literally contained in the stored owned message. The model cannot supply an owner ID or arbitrary source URL. All changes remain `AI_CANDIDATE / PENDING`, default RESTRICTED, requiring separate owner confirmation.

2. **Source validity survives through retrieval.** `PersonalOntologyAssertionGuard` rechecks CHAT_MESSAGE ownership and non-deleted conversation when confirming or evaluating current memory. Deleting a chat removes its source-linked facts from default AI-safe current-memory retrieval. The retained memory can still be explicitly managed/corrected/erased through owner functions; no silent data export or automatic fact resurrection.

3. **On-demand provenance inspection only.** `GET /api/memory/{id}/source-preview` checks ownership of both the assertion and its source. It returns a bounded original message only when the owner clicks “查看聊天来源”, with HTTP no-store and in-memory UI clearing on close/navigation. No eager fetch for private facts; this raw chat preview is **explicitly excluded from MCP**. The precise model-provided substring is validated at intake but **is not separately stored**; source reference points to the original message.

4. **Conservative duplicate prevention.** AI candidate save and final confirmation both compare owner-scoped facts with matching predicate/type and overlapping effective periods, using Unicode NFKC, whitespace normalization and casefold. Same normalized literal cannot be re-submitted as a new candidate or confirmed AI fact. The query is bounded to 200 comparable facts; if the boundary is exceeded, the server fails closed rather than claiming no duplicates. Existing request-key provenance replay checks remain in place.

5. **Read-only preflight without leaking private values.** `POST /api/memory/ai-candidates/inspect` returns only each selected candidate's requestKey and disposition: `NEW`, `DUPLICATE`, `POSSIBLY_RELATED`, or `REVIEW_REQUIRED`. It does not send raw prior memory to model or UI. The “related” hint is a short substring overlap, **not semantic contradiction detection**; it never automatically supersedes an old fact. ChatView blocks known duplicates and ambiguous over-limit candidates from selection, displays related hints, and requires a successful duplicate preflight before batch submit. Backend rechecks before every actual save.

6. **History uses existing lifecycle.** `supersedes_id`, `SUPERSEDED`, `INVALID` and `valid_from/valid_to` already preserve an explicitly approved correction chain. T-008c does not create a second lifecycle, erase past versions, rewrite old effective dates, or auto-correct a memory because the model thinks it is outdated. The first-party owner correction dialog remains responsible for replacement, and final confirm revalidates its predecessor.

## Owner access after a chat source is deleted

Normal AI retrieval intentionally drops facts whose chat evidence has become unavailable, but the stored fact must remain user-manageable. `GET /api/memory/history/normal` is a **separate, owner-click-only, no-store, MCP-excluded** list of up to 100 NORMAL confirmed/invalid/superseded assertions, **without** filtering invalid sources. The UI panel “普通记忆历史与失效来源” is closed by default, clears its data on account/tab change and route exit, and provides correction, invalidation and permanent deletion. It does not affect `listCurrent` and does not make revoked-source facts model-visible. Existing SENSITIVE/RESTRICTED facts remain in the separately opened private management panel.

This is bounded history management, **not** an exhaustive ancestry graph or a chronological lifecycle timeline. Pagination and explicit version-chain visualization are future work.

## Privacy and failure handling

- `AI_CANDIDATE` remains provenance, **not** trust or an AI conclusion that the user is competent/healthy/etc.
- The source preview is not MCP-visible and must never be included in a default AI context bundle. The inspect endpoint returns classifications only, not old private fact text.
- If the original chat is deleted or reference ownership is revoked, source-based facts are filtered from normal retrieval and any pending fact cannot be confirmed without new evidence.
- A source message can contain unrelated personal content; hence preview is user-click-only, a maximum of 2,000 characters, and not included by default.
- Duplicate comparisons consider only overlapping assertions whose evidence references are still valid. Deleted chat messages, revoked task/record/review sources, and invalid/missing source types must not permanently prevent the owner from re-establishing an equivalent statement with fresh evidence. The historical row remains owner-manageable, never silently restored to AI retrieval.
- Existing first-party unsourced AI suggestions remain possible but are clearly distinguished from `CHAT_MESSAGE`-backed assertions; they cannot claim verified chat provenance.
- **Known limit:** normalized-text dedup is not semantic inference, cannot detect all contradictions or paraphrases, and does not guarantee race-free uniqueness under concurrent distinct request keys. A future V32 indexed fingerprint/serializable strategy and end-to-end MySQL concurrency tests are required before claiming a strict global dedup guarantee.
- This feature does not automatically listen to official ChatGPT chats or run unattended background extraction.

## Verification gates

Synthetic JUnit checks: owned quote succeeds; invented quote/foreign owner fails; source type is validated; source references are checked during normal retrieval; deleting source excludes fact; same normalized effective fact produces 409; read-only preflight distinguishes duplicate/related/new; owner-only source preview. Existing AI extraction/security/OAuth/MCP tests and actual MySQL/Flyway tests on **exact head SHA** must pass. Browser confirmation, sensitive data visibility, source deletion, race conditions, and independent privacy review remain unverified until CI/staging acceptance.

No code in this PR changes protected `main`, production configuration, OAuth grant, or real user records.
