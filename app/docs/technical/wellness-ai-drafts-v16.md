# PRP Health AI draft capture (V16)

## Implemented in PR #39

- AI parses text or <=3MB JPEG/PNG/WebP into an **untrusted create-only proposal**: meal, exercise, or body weight. Supported photo recognition depends on the chosen provider/model and must be verified against live API before release.
- Before any business write, the user sees a mutable preview. For meals, choose a local or USDA-imported food item and edit grams; for exercise/weight, edit the relevant fields and date. This is a human-in-the-loop workflow.
- Unknown food names and unknown weights are allowed as **incomplete pending drafts**; nutrition is never fabricated. Confirmation fails if any meal item is unmatched or has non-positive grams. Server ignores model/front-end calories, resolves food ownership and recalculates from the selected food reference.
- The authenticated user has a private draft valid for 15 minutes. PATCH validates a corrected draft using the stored action type and locks the row; POST confirm locks and consumes it in one transaction. The model cannot choose user IDs or SQL, cannot silently update/delete existing health records.
- AI images are sent only on explicit request to the configured provider and are **not stored as historical photos**. This does not make the upstream service private; disclose third-party processing and follow the vendor's data policy.
- Photo estimates, cooked dish oil and branded-food sizes are inherently uncertain. Different foods can have the same or similar name; users must verify the selected preparation state.
- The initial AI writing path is independent from the chat's **read-only, one-message consent** flow. Chat now opens the composer on explicit health-recording requests even without an @ mention. This does **not** grant direct AI mutation authority.
- Opt-in read tools `wellness_trends` and `wellness_body_trends` cover 7/14/30-day windows. Body weight requires a separate `wellness_body` scope, distinct from basic `wellness`, and null means unrecorded.
- No existing API or historic table is overwritten. V16 is additive.

## APIs

- `POST /api/wellness/ai/prepare` multipart: `text` and optional `image`
- `PATCH /api/wellness/ai/drafts/{draftId}` normalized human edits, same stored create action
- `POST /api/wellness/ai/drafts/{draftId}/confirm` one-time confirmation

## Deployment checks

Back up and restore-test `matrix_prp`, verify migrations V1–V14 already applied (or correct reviewed baseline), validate Flyway, apply V15 and V16 in order, verify old user rows unchanged. Run browser/PWA tests on iPhone, real-model photo smoke tests, food cross-user isolation checks, missing-weight draft and expired/replayed confirmation tests. Do not automatically baseline or clean.

## Deferred

AI updating/deleting existing records with before/after review; direct recording with a user-supplied total kcal but no known gram/food; long-term private image archive and device imports; provider-specific live smoke tests.
