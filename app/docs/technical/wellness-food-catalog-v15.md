# PRP food catalog expansion — V15

- **143 additional shared generic reference foods** seeded additively, without altering any previous food, meal or user data. All entries are labelled as **approximate reference values**, not manufacturer nutrition labels, and not official USDA-derived per-item data.
- **91 Chinese ingredient-to-English search aliases** for the optional USDA FoodData Central search service. Only explicit ingredient names are translated; composite dishes are not silently equated with unrelated English dishes.
- USDA FoodData Central supports a broad authoritative US/national and branded food lookup; configured server-side using `MATRIX_PRP_USDA_API_KEY`. It requires a data.gov API key for production; API documentation: https://fdc.nal.usda.gov/api-guide/
- Search only on explicit user action. A chosen USDA record's actual nutrient values are retrieved again by FDC ID server-side before storing; original FDC ID is retained in `source_note` and imported entries belong to the user. Chinese search terms can be used as the local alias for that item; the user must confirm it represents the correct product/preparation.
- FDC records with incomplete energy/protein/carbohydrate/fat grams per 100g are rejected, instead of inferring missing values. Search and import return explicit errors if the service is not configured.
- USDA/US government FoodData Central content is public domain (CC0). Do **not** ingest Open Food Facts dumps into the same private catalog without appropriate ODbL attribution/share-alike analysis. Original FDC page and food ID identify each chosen USDA item.
- The current built-in library does **not** contain every Chinese restaurant recipe or packaged brand. Those vary widely in oil, serving sizes and formulation; manually entered records remain editable. An official or package label beats a generic value.

## QA and rollout

Retain immutable V1–V7 legacy mirrors, add V15 to migration manifest, and run MySQL legacy-data preservation tests. Back up and restore-test `matrix_prp`, check Flyway schema history and validate migrations, then enable after approval. **Never** recreate MySQL volumes or run `flyway clean`.
