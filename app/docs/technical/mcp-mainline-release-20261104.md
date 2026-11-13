# Authorized mainline application release

On 2026-11-04 the owner requested merging and publishing the ChatGPT write chain,
then explicitly selected keeping ChatGPT on the existing test database and only
publishing mainline application code. PR #151 merged as 3ea90c9 after 33 successful
unified CI jobs. Production SELECT-only inspection found V24, 18 successful
Flyway history entries and zero failures. The installed controller digest matches
the approved manifest c329836ed2f48296e5ab505451aab3c59b33db7f7c20aba5ae7c2b1ec80622e2.
Restricted production check run 41848601916 succeeded; this is not migration or
publication acceptance.

This release removes the temporary collaboration-review publication hold through
a separate PR. No collaboration controller/state proposal is included or installed.
The deployment workflow, production environment, SSH inventory, manifest and
controller remain unchanged. Existing backup/restore, migration preservation and
health gates must pass on the exact final main SHA before reporting a release.
An uninstalled controller candidate still cannot publish, and future holds remain
supported by the existing release-control tests.

MCP/OAuth/write defaults remain false in the formal application. Do not move the
test MCP route, test database, Keycloak clients, grants or user bindings. The live
ChatGPT test connection remains separate from the formal website. Production MCP
activation and production-account pairing require a later explicit rollout.

V25-V29 are additive declared empty-table migrations; existing migration bytes
are unchanged. The release controller must back up actual production data and
rehearse on an isolated restored database. Do not use synthetic CI as that proof.
If a preflight fails, stop before cutover. Do not restore old SQL over migrated
production or attempt cross-schema application rollback. Follow the controller's
recorded recovery phase and preserve all backups.

Known functional gap: generic wellness RECORD text does not populate structured
meal/calorie totals (#152). Remaining branch assessment is tracked in #153.
