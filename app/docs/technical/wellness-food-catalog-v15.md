# PRP Wellness Food Catalog — V15

* Existing V7 reference rows and every user's data are preserved. V15 only adds new shared reference foods when the same name/preparation pair is absent.
* This migration contains **143 additional generic food-reference entries** (Chinese names, per 100g). Values are explicitly approximate; they are NOT copied from, or represented as, USDA verified values. Prepared dishes can vary significantly. Existing V7 entries may overlap by food name with different preparation status.
* Search for authoritative additional foods through USDA FoodData Central. Their API is CC0/public domain: https://fdc.nal.usda.gov/api-guide/ . Configure server environment variable `MATRIX_PRP_USDA_API_KEY` with a private data.gov key. The key is never returned to the web client.
* FoodData Central searches only run when the user clicks Search and import. This avoids leaking queries to a third party on every keystroke and reduces external rate-limit risk. The FDC ID and provenance are stored in the imported food's source note. Imported records belong to the current user.
* No Open Food Facts dump is mixed into the database: its database ODbL conditions require a separate license/compliance design.
* Operations: backup and restore-test matrix_prp, verify Flyway state, apply V15 once through established migration process, verify counts, then deploy Java + Web. Do not recreate the MySQL volume or run automatic Flyway baseline.
* Tests: existing wellness calculation and migration suites, USDA field extraction unit test, web typecheck/build, real-MySQL Flyway/legacy-preservation verification.
