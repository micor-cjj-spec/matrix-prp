# PRP-AI-09 · Spring AI multimodal image recognition (opt-in)

## Scope
- Add a separate image-only Spring AI 1.1.8 OpenAI-compatible Chat Completions
  adapter for the **existing** PRP wellness create-draft API.
- Allow the exact server-side combination of DeepSeek `deepseek-flash`,
  OpenAI `gpt-4.1-mini` / `gpt-4.1`, and Kimi CN/global `kimi-k2.5`.
  This is **not** a seven-provider picture capability claim; all other
  providers continue to fail closed on unsupported image use.
- A request includes one UserMessage image (inline base64 data URI) and a
  separate system instruction. Only validated JPEG/PNG/WebP bytes <=3 MB are
  accepted. No arbitrary remote image URL, arbitrary model, or endpoint.
- Preserve authenticated owner, per-user request/token quota, 15-minute
  draft expiry, 30-item validation, food matching and calorie reconciliation,
  edit-before-confirm, and the one-time owner-scoped confirmation transaction.
  Photos are not stored. Model output never directly commits health data.

## Production policy (default OFF)
```properties
matrix-prp.ai.spring-ai.vision-enabled=false
# Enable only after the real-provider and production device acceptance below.
MATRIX_PRP_AI_SPRING_AI_VISION_ENABLED=true
```

When disabled, image uploads continue through the previous native adapter.
Text-only wellness draft handling remains on the independent
`MATRIX_PRP_AI_SPRING_AI_STRUCTURED_ENABLED` toggle.
To roll back the Spring AI image route for subsequent requests, set
`MATRIX_PRP_AI_SPRING_AI_VISION_ENABLED=false`; this does not modify records.

## Offline verification
The loopback tests invoke the **real Spring AI OpenAI adapter** against local
stub endpoints for all four supported provider entries. Verify:
1. System/user roles, model name, actual encoded binary image as
   `data:image/png;base64,....`, and no secret in the request body.
2. One upstream request per operation, provider 429 classification,
   empty response handling, and no retry.
3. Unsupported provider/model and oversized/unsupported image rejection
   before any network call.
4. Existing wellness database tests, owner-scoped draft and confirmation,
   quotas, 30-item safety, migrations and Web/PWA CI are still green.

## Still required before toggling on in production
- Test **real configured paid credentials** for DeepSeek, OpenAI and Kimi
  independently, observing provider-specific vision image acceptance and
  completion text, especially API-region and model availability. Loopback
  fixtures do not prove real provider interoperability.
- On iPhone PWA, verify JPEG/PNG/WebP image uploads, client MIME behavior,
  3 MB validation, photos containing multiple dishes, editable incomplete
  draft, confirmation, and no hidden record mutation.
- Inspect sanitized logs and check that uploaded image bytes/API keys do not
  enter application logs or persistent file storage.
- Keep existing protected publication, backups, migration, SSH and
  production release gates intact; do not enable based solely on CI.

## Out of scope
- Persistent photo albums and historical image retrieval.
- Images sent through ordinary chat or through arbitrary AI tools.
- Direct AI write, cross-tenant reads, independent OCR, or food nutrition
  inference without explicit human confirmation.
