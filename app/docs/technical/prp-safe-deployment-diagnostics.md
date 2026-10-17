# PRP: Safe production deployment diagnostics (P0)

## Goal and limits

The existing deployment controller writes the complete Python traceback to a root-only
`/var/lib/matrix-prp-deploy/last-error.log`, but the GitHub Actions deployment identity
has a forced-command SSH gateway and cannot read that file. This is intentional.
The repository's `app/deploy/server-release.py` is not a byte-identical copy of the
installed production controller; never overwrite the latter from this repository.

This change introduces:

1. An Actions **failure-only** step that attempts only the fixed `diagnose`
   command after independent installation. It publishes only a
   **strictly validated JSON report** and GitHub Step Summary.
2. A root-owned `prp-diagnose` helper that reads a single fixed error-log path and emits
   only a known error code, an approved pipeline stage, a *table name* where applicable,
   a class name, and a log timestamp. It NEVER prints log lines, SQL, user IDs,
   primary keys, user content, credentials, filenames selected by callers or stack traces.
3. Optional explicit authorization of the fixed `diagnose` command in the server's
   forced-command gateway. **No arbitrary SSH shell or sudo, SFTP, port forwarding,
   or controller replacement.**

In a public GitHub repository, **never publish raw logs, raw stderr, backups, traces, or
full database rows** to Actions outputs or artifacts. Actions cannot view root-only
records without the separately authorized read-only helper.

## Behavior before the helper is installed

When a publish fails, Actions attempts only the fixed `ssh ... diagnose`
command. On older gateways this returns an error, which is discarded. Actions
then publishes an allowlisted "diagnostic unavailable" report. It does **not**
request raw logs or invoke the existing `status` command after a failure.

**Why avoid status?** The current installed controller's global exception handler
writes `last-error.log` with mode `w`. A failure while probing status could
overwrite the original deployment traceback and destroy the evidence. Successful
releases retain their normal status verification.

Once the administrator installs `diagnose`, the rendered report includes the
sanitized failure code/stage/object. Until then, the exact assertion remains
unavailable without authorized administrator inspection.

## Reviewable installer (does not auto-apply)

The branch now contains `app/deploy/admin_install_diagnostic.sh`. It
accepts an **explicit absolute path to the installed root-owned forced-command
gateway**; the repository's reference gateway is not an acceptable replacement.
The initial `--check` operation validates the approved controller hash,
the installed gateway's structure, the helper source, sudoers syntax and the
**exact one-line candidate diff**, without changing production files.

After the administrator reviews the diff and approves the fixed sudoers rule,
use `--apply` with the **same** gateway path. This creates a root-only dated
backup under `/var/backups/prp-diagnose/`, installs the helper and
exact-command sudoers entry, patches only the confirmed gateway anchor, and
verifies the original controller checksum. An installation failure attempts
to restore the gateway and remove new helper/sudoers entries.

Example (requires an administrator-managed checked-out copy of this branch,
pinned to its audited commit SHA; never run an unreviewed `curl | bash`):

```bash
sudo bash app/deploy/admin_install_diagnostic.sh --check /absolute/installed/ssh-gateway
# Review the displayed diff and sudoers scope before continuing.
sudo bash app/deploy/admin_install_diagnostic.sh --apply /absolute/installed/ssh-gateway
```

Do not run `--apply` until the actual installed gateway path and source
have been verified. Keep an independent root shell open while validating
the new SSH forced command. After installation, explicitly verify denied
shell, SFTP, and argument-bearing diagnose requests as described below.

## One-time administrator-only setup

Do not perform these steps from an ordinary PR or GitHub Action. The original
root-owned production controller `/usr/local/sbin/prp-release` and its SHA256
approval manifest must remain unchanged.

1. On an isolated host, inspect `app/deploy/read_only_diagnostic.py` and
   `app/deploy/ssh-gateway.sh`. Run
   `python3 -m unittest discover -s app/deploy -p 'test_*.py' -v`.
   Confirm the helper has no external commands, no user-supplied path arguments, and
   no raw-log stdout. Record the reviewed helper's SHA256.
2. On production, make a root-only backup of the *installed* forced-command
   gateway and of existing sudoers entries. Verify the current controller digest
   against `app/deploy/controller-manifest.json` **before and after** this change.
   Do **not** replace the installed gateway with the repository reference file.
3. After independent approval, install the vetted helper as the root-owned executable
   `/usr/local/sbin/prp-diagnose` (owner `root:root`, mode `0755`) and verify
   its SHA256. Keep `last-error.log` and `/var/lib/matrix-prp-deploy`
   inaccessible to the deployment SSH account.
4. Carefully amend the currently installed root-owned forced SSH gateway with this
   **single literal case**, preserving all previous cases and permission boundaries:

   ```sh
   diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;
   ```

   Do not accept parameters, wildcards or alternate filenames. Never add
   `cat`, `tail`, `bash`, `sh` or SFTP rights.
5. Add one reviewed **exact-command** sudoers entry for the restricted account:

   ```sudoers
   prp-deploy ALL=(root) NOPASSWD: /usr/local/sbin/prp-diagnose ""
   ```

   Apply it through `visudo` syntax validation; **do not use `NOPASSWD: ALL`**.
   Preserve the original deploy/rollback sudoers lines unchanged.
6. Confirm an ordinary `status` and `check` still work and that
   `controller-sha256` still matches the approved digest. Verify a forced SSH
   `diagnose` invocation returns **one JSON object only**, with `schema_version:1`,
   one of the fixed codes, and no private row IDs. Check arbitrary shell, SFTP,
   port-forwarding and `diagnose anything` are still denied.
7. If anything differs from review, restore the backed-up gateway and sudoers
   independently; do not relax GitHub Actions deployment or database integrity gates.

Because `prp-diagnose` uses the file's modification time, a log older than two hours
will report `STALE_DIAGNOSTIC` instead of misattributing an old failure to a new run.

## How AI can troubleshoot after setup

1. Open the failed **Deploy PRP** GitHub Actions run.
2. Read its `PRP production deployment diagnosis (sanitized)` Step Summary.
3. Open its `prp-safe-deployment-diagnosis` artifact if structured details are needed.
4. Correlate `code`, `stage`, `table`, diagnostic timestamp and the intended
   release SHA. Production runtime metadata is intentionally unavailable on
   failed publishes without an independently reviewed read-only source.
5. If `code` is unknown, stale, or malformed, ask the authorized administrator for
   a *specific* root-only traceback excerpt. Never guess an unobserved assertion.

## Deployment safety and current V18/V19 blocker

The installed controller still runs the V17 policy and rejects the new
`prp_ai_conversation_meta` (V18) and `prp_wellness_ai_action_targets` (V19) tables.
The current V18 creates a separate empty metadata table; it does not change old
conversation rows. V19 can legitimately backfill nonempty owner-scoped action
links using durable meal idempotency keys. A future controller patch must verify
those exact backfill rows, not merely permit every new table or require all new
tables to be empty. The controller fix requires separate administrator approval.
The production rollout remains blocked by its preservation preflight, so
**merging this PR would trigger the existing automatic deploy workflow again**.
Keep this feature PR unmerged until there is an approved way to prevent an
unintended V18 retry or the underlying preservation fault is resolved. No root
controller modifications, schema changes, or failed-release retries are performed
by this diagnostic feature itself.

This feature does not disable row fingerprint assertions, migrations, rollback
safety, controller attestation, release identity verification, or production approval.

## Review update 2026-10-16

The feature branch is synchronized with main `a9c2fde2d813849df2c5e4162a9741f03a442175`.
The server gateway is `/usr/local/bin/prp-deploy-gateway`, root:root 0755. Its
controller-sha256 case is multiline; the installer now recognizes exactly the
reviewed one-line and multiline forms and refuses unknown/duplicate anchors.
Existing deploy/rollback cases are preserved byte-for-byte. The install takes
the existing deployment lock, backs up the gateway and sudoers directory, and
adds only a separate no-argument sudo rule (`""` means no command arguments).
`--check` does not install or modify production files.

The helper pins `/usr/bin/python3 -I`, refuses symbolic links, FIFOs and writable
or incorrectly owned logs, and reads only the fixed log path. Both host and
renderer use the same explicit migration-derived table-name allowlist. Unknown
identifiers that merely start with `prp_` are never published. Unknown new-table
assertions have a distinct `UNEXPECTED_BUSINESS_TABLE` code without guessing the
new table from source-code lines in the traceback.

The renderer requires valid attempt and diagnostic timestamps. Even a log from
one second before the publish attempt is stale; missing timestamps are unavailable.
It assumes bounded host/runner clock skew only for future timestamp rejection,
never uses skew tolerance to attribute a prior error to a new attempt. Diagnosis
SSH is bounded to 20 seconds with a file-size limit. Diagnostic collection and
artifact upload are best-effort and do not change the failed deploy outcome.
The CI diagnostics job exercises parser privacy, freshness, file permissions,
actual shell command rejection, both gateway layouts, and controller attestation.

After approval, install diagnostics FIRST while the attested controller still
matches `d3e5113cd8d37daabc179a2503dc36d42d1596db822239839b535525e3da75c6`.
Do not change the manifest to bypass a mismatch. A separately approved controller
patch needs its own before/after hashes, isolated migration reproduction and a
subsequent independently reviewed manifest update before production deployment.
Do not merge this PR until installation, review and CI are complete and the
automatic main deployment is prepared. No production retry is needed to inspect
the existing failed run. Old logs beyond the two-hour TTL remain stale.

## Approved installation and blocking SSH gate (2026-10-16)

The administrator approved A, B, and the adjusted verification order. The diagnostic
helper is installed with the previously reviewed hash and the gateway/sudoers scope
is unchanged except for the fixed no-argument command. B has now been atomically
installed and independently attested as
`7d23ea686b7eca6e66619979357953a0a18fc366d4896f900ea6cae743b396d1`.
Only the reviewed `snapshot` and `assert_preserved` functions changed. Installation
kept the running application and V17 database unchanged. The controller manifest
now binds this actual installed hash; it was not changed to bypass a mismatch.

`verify_ssh_boundary.py` executes in the existing production-environment publish
job after checkout/identity setup and before ANY production controller operation.
It validates controller-sha256 against the manifest, validates the fixed diagnostic
JSON with the same explicit enums/table allowlist, and checks exact gateway denials
for shell, SFTP (command and subsystem), parameters and injection. It verifies the
`direct-tcpip` channel used by local forwarding with `ssh -W`, plus remote forwarding.
The targets are non-business loopback port 1; remote listen port 0 requests an
otherwise valid ephemeral listener. No application payload or business record is
sent. A wrongly accepted remote forward times out and disconnects, failing the gate.

Every SSH invocation has a 20-second subprocess deadline, strict host-key checking,
batch authentication, and explicit identity selection. Command denials require both
exit 2 AND the actual installed gateway denial marker, with no stdout. Forwarding
requires exit 255 AND the expected OpenSSH permission-denial marker, with no stdout.
Authentication, host-key, DNS/connection failures and timeouts have separate fixed
error codes and never count as successful rejection. Raw stderr/stdout, host names,
private keys, tokens and diagnostic contents are not printed by the verifier.

The gate has no continue-on-error and uses a fail-fast shell. Failure leaves
`production_operation` skipped: no backup, migration, or release switch occurs.
The existing controller attestation remains as a second check after this gate.
Checks on PR branches cannot access production secrets; the environment remains
main-only. The old manual `check` action retains its existing behavior (it does
not check out deploy sources); this new gate runs for deploy/promote and main
CI-triggered publication. A failure is a STOP for review, never a reason to bypass
the gate or roll back the database.
