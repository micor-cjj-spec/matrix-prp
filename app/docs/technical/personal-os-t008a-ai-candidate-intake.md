# Personal OS T-008a — AI knowledge candidate intake (DRAFT / NOT ACTIVATED)

Tracks [T-008 #228](https://github.com/micor-cjj-spec/matrix-prp/issues/228), parent [#181](https://github.com/micor-cjj-spec/matrix-prp/issues/181). This implementation is stacked on the unmerged Personal OS V31 integration candidate #206, **not** production main.

**No main merge, no production deploy, no OAuth/Keycloak change, no actual personal conversation or secrets committed.**

## What this slice implements

A first-party, user-authenticated API accepts **already-structured, model-suggested** knowledge candidates:

`POST /api/memory/ai-candidates` — an array of 1–5 candidates.

Each item has only the allowed fields:

```json
{
  "predicate": "DECLARES_SKILL",
  "value": "Synthetic Java",
  "validFrom": null,
  "validTo": null,
  "sensitivity": "RESTRICTED",
  "requestKey": "synthetic-unique-20261121"
}
```

Other supported predicates: `PREFERS`, `HAS_BACKGROUND`. Owner's `PERSON` ID, `LITERAL` object, `USER_INPUT` evidence and null evidence reference are **forced server-side**. The model cannot claim independently verified entity IDs or another user, fabricate record/task source IDs, or define arbitrary ontology relationships. Maximum value length: 256 characters, no control characters.

Every persisted row:
- has `origin=AI_CANDIDATE`, **not** `USER_CONFIRMED`;
- starts `status=PENDING`, never auto-confirmed;
- defaults to `sensitivity=RESTRICTED` when omitted; `NORMAL` must be explicitly specified before the owner's existing separate confirmation action;
- remains invisible to existing `listCurrent`, T-005 default context and MCP read tools until eligible;
- carries a per-owner idempotency key; existing keys with a different payload **or provenance** fail with 409.

The batch is bounded and processed under a single transaction. The existing first-party `GET /api/memory/candidates`, `POST /api/memory/{id}/confirm`, invalidation, correction and deletion remain the sole review/confirmation path. The new endpoint is **explicitly excluded** from MCP's route registry.

## Intentional limitations

This does **not** yet accept raw chat messages, run a model extractor, intercept every ChatGPT chat, deduplicate semantically equivalent phrases, or submit through an OAuth MCP tool. It only provides the safe persistence boundary required by those later workflows. In particular, do **not** present this as an automatic learning feature to users.

Do not place private chat excerpts in the request body: structured assertions only. The current assertion schema does not persist a raw chat transcript or a verifiable per-message provenance identifier. `AI_CANDIDATE` denotes the submission route, **not** independently verified model origin, confidence or a user-certified fact.

## Later T-008b / T-008c

- Explicit owner-chosen excerpt and provider/model preview; outbound model consent must be separate from local storage permission.
- Bounded extraction prompt + rigid JSON validation; candidate evidence quotes, source time and classification displayed to user before `POST /api/memory/ai-candidates`.
- UI must visibly show candidate `origin`, sensitivity and source limitations before owner presses existing confirm. If the user wants NORMAL retrieval, ask explicitly rather than silently upgrading the default.
- Duplicate/conflict detection, supersession with human review, privacy revocation and linked relationship validation. No automatic writes, and no self-modifying ontology schema.
- Separately reviewed OAuth scope, user grant, operator gates and approval flow would be required for an eventual MCP candidate-preparation tool.

## Gate checklist

Full CI on exact SHA, positive and negative security tests, MySQL V31 real DB rollback/idempotence integration, first-party UI audit, independent review, and explicit release approval. Until then this remains a Draft and should not be enabled or deployed.
