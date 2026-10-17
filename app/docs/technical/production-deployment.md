# Production release and chat-driven operations

The release path is a reviewed PR merged to `main`, successful CI, an artifact
built from that exact commit, then the production deployment workflow. The
`production` environment retains its existing protection rules. Deployment SSH
credentials remain in GitHub Secrets; coding agents must not retrieve them.

A connected coding session can receive a request such as: "Deploy current main
to Matrix PRP production, inspect failures, preserve all historical data and
security gates, and return the actual running commit and migration version."
The session must have repository write/workflow access to carry out that request.
A chat without repository/workflow tools cannot execute a release by text alone.
Routine releases need no administrator SSH operation once compatibility has been
reviewed. Missing permissions must be reported precisely, never worked around.

## Application releases

1. Refresh `main`, the latest CI/deploy runs and production evidence.
2. Make changes on an isolated branch, test, review and merge through existing
   repository policies. Successful main push CI automatically builds/publishes.
3. For an explicit retry use `deploy-prp.yml` on `main` with `action=deploy`.
   `action=build` only builds; `action=check` performs the existing production
   check. `promote` requires an exact successful candidate run for current main.
4. Wait for publish and independent production acceptance. Verify the current
   release SHA, file hashes, Flyway history, systemd, Nginx, authenticated APIs,
   private video access and preservation evidence. Never treat skipped publish
   or build/CI success as a deployment.

## Schema changes and controller governance

The installed controller and legacy repository `server-release.py` differ.
`approved/prp-release.py` records exact reviewed production bytes for tests;
it does not deploy itself. CI checks its hash against the approved manifest,
pins reviewed V20/V21 SQL (canonical LF), rejects duplicate versions and requires
exact create-empty contracts for V22 and later. The legacy ceiling does not need
to change for each ordinary new table. A `candidate_controller` is CI-only, cannot
attest the installed controller, and cannot pass publication readiness without
an explicit publication hold. See the versioned migration policy for details.

V21 controller compatibility has been installed after an administrator-authorized,
exact one-line review and restored-copy rehearsal. It permits exactly three
initially-empty finance staging/source-link tables, retaining V20 vocal and V19
backfill checks. The production application/database remain V20 until a separate
application publication is authorized. Main's manifest must be approved in sync
with the installed controller and independently measured SSH inventory before
publication; candidate CI success never grants live approval. Before V22 or later,
repeat compatibility review and restored-copy rehearsal; never raise the version
ceiling merely to make CI pass.

For a necessary root-owned controller change: independently measure installed
bytes, prepare the smallest exact diff, test preservation guards, back up the
controller/config/database, rehearse on an isolated restored database, obtain
the required administrator authorization and install atomically. Preserve owner,
group/mode and verify unchanged service/database/SSH configuration. Never replace
the controller wholesale with `server-release.py`.

Controller replacement changes the live SSH inventory digest (including ctime).
Independently remeasure the root inventory and review that only the controller
record changed; approve the exact new controller and policy digests in the PR.
Fresh nonce-bound restricted-identity proofs and full SSH/SFTP/forwarding tests
remain mandatory. A candidate proof is never self-approving.

## V20 repair and rollback

`admin_upgrade_v20_controller.py` is a one-time administrator-only procedure,
not callable through the deploy gateway. It accepts only the exact old digest
`7d23ea686b7eca6e66619979357953a0a18fc366d4896f900ea6cae743b396d1`
and reviewed new digest
`bafcd9d7d79d478cf0751db9c49d2456f92a82cf6c051a4876d38fedaa7c566b`.
It changes one allowlist entry for `prp_vocal_takes`, leaving its initial-empty
guard and all existing preservation checks intact. It validates staged main
artifact file checksums, creates a full backup, rehearses V19 -> V20 on a restored
copy, and requires unchanged production state before atomically installing.

The root-only review directory is `/root/prp-v20-review`. Run `check` first;
`apply --approved-sha256 <new digest>` requires reviewed staged candidate bytes.
Backups and the receipt live in `controller-backup`. To restore controller bytes
use `rollback --approved-sha256 <old digest>`, then independently remeasure and
review the SSH baseline again (ctime changes even when old bytes are restored).
This does not roll back database/application state. Do not restore a pre-V20 SQL
dump over a live V20 database or use cross-schema application rollback. A failed
cutover whose database changed requires controlled forward recovery and review.

Raw SQL backups, credentials, row contents, SSH logs and configuration secrets
stay root-only on the server; Actions exports only the existing sanitized schema.


## V21 controller-only upgrade

The exact reviewed one-line upgrade permits the initially-empty tables
`prp_finance_import_batches`, `prp_finance_import_rows`, and
`prp_finance_source_links`. It preserves all historical full-row, V19 backfill,
video ownership, nonempty-new-table and unknown-table guards.

The administrator-only `admin_upgrade_v21_controller.py` requires installed
controller SHA256
`bafcd9d7d79d478cf0751db9c49d2456f92a82cf6c051a4876d38fedaa7c566b`
and exact reviewed candidate SHA256
`ae01801d85b01a6f978f0d030aad052b72e778f3e50185daf33445c2d32d7f7a`.
It validates the cached trusted-main V21 artifact, backs up the controller/config
and full database, restores/migrates only a unique scratch database, checks
historical integrity, cleans up its scratch grants, and requires unchanged live
V20 data/service before atomically changing the controller. It does not deploy
an application, migrate the production database, or restart any service.

Review files, original controller and receipt are root-only under
`/root/prp-v21-review/controller-backup`. Controller-byte rollback is
`python3 -I /root/prp-v21-review/admin_upgrade_v21_controller.py rollback
--approved-sha256 bafcd9d7d79d478cf0751db9c49d2456f92a82cf6c051a4876d38fedaa7c566b`
(on one command line). This never restores SQL. Independently remeasure and
review the SSH inventory after any controller replacement, including rollback.

A controller-only approval PR may merge without publishing an application only
when the explicit publication hold gate is present, tested and enforced. Without
that hold, keep it unmerged until application publication is requested. Main's
controller/policy hashes must match independent installed measurements before
real restricted-identity acceptance. Preserve the existing main-only production
environment branch policy; never expand it for earlier tests. Installed capability,
manifest approval, live SSH acceptance and application publication are separate
recorded stages.

## Versioned migration contracts

The controller supports stable, bounded create-empty contracts for V22 onward. See [versioned migration policy](versioned-migration-policy.md) for the supported SQL subset, exact contract format, trust model, administrator installer/rollback and one-time publication hold. This replaces per-table controller edits for ordinary additive empty tables; unsupported transformations remain fail-closed.
