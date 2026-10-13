# Health AI write drafts — V16 (initial create-only release)

Design:
- AI is an untrusted parser. The only permitted actions are `meal.create`, `exercise.create`, `metric.create`.
- A caller submits plain text and optionally a JPEG/PNG/WebP image (<=3MB). The backend validates file signature, uses the configured AI provider from the authenticated user's settings, and records ONLY a normalized write proposal; images are not stored.
- DeepSeek photo calls use **deepseek-flash** (a vision-capable model); ordinary text uses the currently selected model. OpenAI GPT-4.1 and Kimi K2.5 are allowed for images. Unsupported selected vision models fail closed.
- The model cannot choose userId, credentials, SQL, endpoints or nutritional values. Every meal item resolves to a locally accessible foodId; calories are computed server-side using existing NutritionMath. Unknown foods/weights fail closed and require manual correction or importing the food.
- The proposal is private to the current user, valid 15 minutes, and one-time confirm. A row lock, transaction and existing meal idempotency key guard prevent repeat confirmed writes.
- Existing wellness CRUD APIs remain untouched and AI is not granted silent update/delete. Users keep using the authenticated manual forms for update/delete.
- This opt-in flow forwards text and optional images to the selected AI provider. Do not send health records beyond the scope of the user's submitted text/image.
- V16 is additive; backup, restore-test and verify Flyway migration state before production application.
- Next phase: editable pending-draft card, AI correction/update/delete proposals with before/after previews, photo history with private media retention controls, automated external-food synonym matching and full integration tests.

API:
- `POST /api/wellness/ai/prepare` multipart text, image?: file
- `POST /api/wellness/ai/drafts/{draftId}/confirm` one-time user confirmation
- The server returns only normalized draft fields and private PRP deep link after successful saving.
