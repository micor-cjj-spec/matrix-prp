# Matrix PRP deployment invariants

For any Flyway migration or deployment change, read
`app/docs/technical/versioned-migration-policy.md` and `app/deploy/AGENTS.md`.

From V22, ordinary new empty tables require an exact `create-empty` rule in
`app/deploy/migration-policy.json`, not another production controller edit.
Keep historical SQL/rules immutable. Backfills and old table/data changes require
specialist preservation review. Do not relax unknown/missing-evidence refusals.

The legacy `app/deploy/server-release.py` is not the installed controller. Never
copy it over production. Controller hashes/policy baselines need independent
administrator measurement, backup, isolated rehearsal and applicable authorization.

If `app/deploy/publication-hold.json` exists, application publication is deliberately
held. Remove it through a reviewed PR only when application publication is requested.
Do not report a held/skipped workflow as a deployment. Keep SSH keys in Secrets,
main-only production protection, restricted commands and all data-integrity gates.
