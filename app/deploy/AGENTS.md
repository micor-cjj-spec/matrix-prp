# Production deployment instructions for coding agents

Read `app/docs/technical/production-deployment.md` before changing a migration,
the controller manifest, deployment workflows, or production configuration.

The installed root-owned controller is independently governed. The legacy
`server-release.py` is NOT an approved replacement for it. The exact reviewed
controller in `approved/prp-release.py` is an audit/test fixture, not an automatic
installer. Never copy either file into production without the administrator-only
review/install procedure, exact digest approval, backup and isolated rehearsal.

Every new Flyway version requires explicit controller compatibility review in
CI. Do not raise the reviewed version ceiling merely to make CI pass. Keep
unknown tables, nonempty newly created empty-only tables, historical row changes,
ownership changes and missing evidence fail-closed. Verify any pending draft
migration version collision before merging.

Use the existing trusted-main CI -> build -> production publish workflow. Existing
GitHub environment protections and restricted SSH identity remain mandatory.
Do not request, generate or export deployment private keys. Do not grant shell,
SFTP, forwarding, extra sudo privileges or GitHub Actions administrator access.

On a request to deploy, inspect latest main and failed Actions, repair reviewed
code, run tests, and use the existing workflows. Report success only with actual
production commit/schema/health and data-integrity evidence. A green CI, merged
PR, skipped publish or empty SFTP response is not successful publication.
