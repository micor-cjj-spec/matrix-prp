# PRP-AI-08 · Spring AI non-streaming structured text migration

## Scope

Route three previously independent model calls through
`SpringAiStructuredModelClient` (Spring AI **1.1.8**):
1. Practice/question-bank AI generation (draft questions, not guaranteed correct)
   and question explanations. Keep `PracticeService.bank` owner check **before**
   paid model request; preserve 20/day per-user atomic DB admission, fail-closed
   schema/question validation and draft review status.
2. Wellness text-only draft interpretation (meal, exercise, body metric). Keep
   current consent-required draft storage, 15-minute expiry, 30-food-item limit,
   source-based calorie reconciliation and explicit user confirmation.
3. Wellness owner-scoped **preview** edits. Keep service-side field whitelist,
   owner checks, before/after validation, draft expiry and confirm-to-save.

All 7 providers (including DeepSeek, Qwen, OpenAI, Gemini, Kimi CN/global and
Anthropic) use the fixed provider catalog and one-shot non-streaming Spring AI
calls. No automatic retries, framework tool calls, arbitrary outbound hosts,
silent native fallback, cross-user key caching or direct writes.

## Safety and rollback

The new non-streaming adapter uses one request per call, bounded messages and
responses, provider rate-limit translation, sanitized HTTP errors, per-request
model/key, explicit `NeverRetryPolicy` and bounded read timeout.

```properties
matrix-prp.ai.spring-ai.structured-enabled=true
```
Emergency rollback, preserving all prior business validators and DB records:

```bash
MATRIX_PRP_AI_SPRING_AI_STRUCTURED_ENABLED=false
```

Existing `test` profile remains on original mock-compatible routes; dedicated
loopback tests cover Spring AI per-provider request/response with 429 and
credential separation.

## Explicitly not migrated

**Photo recognition is multimodal**: it currently builds a provider-specific
image payload and supports a DeepSeek-specific image model. The old vision
request remains unchanged until image encoding, model support and 3 MB input
limits are verified using a separate loopback + real-provider acceptance.
An uploaded picture will not be silently converted into a text-only prompt.
No additional AI model/API keys are supplied by this patch.

Other structured AI features must not be described as migrated until their
respective call sites are audited and tested.
