# PRP: Safe production deployment diagnostics (P0)

## Goal and limits

The existing deployment controller writes the complete Python traceback to a root-only
\`/var/lib/matrix-prp-deploy/last-error.log\`, but the GitHub Actions deployment identity
has a forced-command SSH gateway and cannot read that file. This is intentional.
The repository's \`app/deploy/server-release.py\` is not a byte-identical copy of the
installed production controller; never overwrite the latter from this repository.

This change introduces:

1. An Actions **failure-only** step that invokes the already permitted \`status\` command,
   plus optional fixed \`diagnose\` if independently installed. It publishes only a
   **strictly validated JSON report** and GitHub Step Summary.
2. A root-owned \`prp-diagnose\` helper that reads a single fixed error-log path and emits
   only a known error code, an approved pipeline stage, a *table name* where applicable,
   a class name, and a log timestamp. It NEVER prints log lines, SQL, user IDs,
   primary keys, user content, credentials, filenames selected by callers or stack traces.
3. Optional explicit authorization of the fixed \`diagnose\` command in the server's
   forced-command gateway. **No arbitrary SSH shell or sudo, SFTP, port forwarding,
   or controller replacement.**

In a public GitHub repository, **never publish raw logs, raw stderr, backups, traces, or
full database rows** to Actions outputs or artifacts. Actions cannot view root-only
records without the separately authorized read-only helper.

## Status without server changes

A failed publish can already use the existing \`status\` command. The new workflow:
- tries the exact command \`ssh ... diagnose\` and discards any rejection text;
- calls the existing \`ssh ... status\`;
- sanitizes both results with \`app/deploy/render_safe_diagnostic.py\`;
- writes only sanitized details to the Actions Summary and \`prp-safe-deployment-diagnosis\` artifact.

Before installation, the report says that the diagnostic command is unavailable.
**This does not reveal the exact failing assertion.** Its benefit is immediate
visibility of the runtime release, deployed commit, service status and schema version.

## One-time administrator-only setup

Do not perform these steps from an ordinary PR or GitHub Action. The original
root-owned production controller \`/usr/local/sbin/prp-release\` and its SHA256
approval manifest must remain unchanged.

1. On an isolated host, inspect \`app/deploy/read_only_diagnostic.py\` and
   \`app/deploy/ssh-gateway.sh\`. Run
   \`python3 -m unittest discover -s app/deploy -p 'test_*.py' -v\`.
   Confirm the helper has no external commands, no user-supplied path arguments, and
   no raw-log stdout. Record the reviewed helper's SHA256.
2. On production, make a root-only backup of the *installed* forced-command
   gateway and of existing sudoers entries. Verify the current controller digest
   against \`app/deploy/controller-manifest.json\` **before and after** this change.
   Do **not** replace the installed gateway with the repository reference file.
3. After independent approval, install the vetted helper as the root-owned executable
   \`/usr/local/sbin/prp-diagnose\` (owner \`root:root\`, mode \`0755\`) and verify
   its SHA256. Keep \`last-error.log\` and \`/var/lib/matrix-prp-deploy\`
   inaccessible to the deployment SSH account.
4. Carefully amend the currently installed root-owned forced SSH gateway with this
   **single literal case**, preserving all previous cases and permission boundaries:

   \`\`\`sh
   diagnose) exec sudo -n /usr/local/sbin/prp-diagnose ;;
   \`\`\`

   Do not accept parameters, wildcards or alternate filenames. Never add
   \`cat\`, \`tail\`, \`bash\`, \`sh\` or SFTP rights.
5. Add one reviewed **exact-command** sudoers entry for the restricted account:

   \`\`\`sudoers
   prp-deploy ALL=(root) NOPASSWD: /usr/local/sbin/prp-diagnose
   \`\`\`

   Apply it through \`visudo\` syntax validation; **do not use \`NOPASSWD: ALL\`**.
   Preserve the original deploy/rollback sudoers lines unchanged.
6. Confirm an ordinary \`status\` and \`check\` still work and that
   \`controller-sha256\` still matches the approved digest. Verify a forced SSH
   \`diagnose\` invocation returns **one JSON object only**, with \`schema_version:1\`,
   one of the fixed codes, and no private row IDs. Check arbitrary shell, SFTP,
   port-forwarding and \`diagnose anything\` are still denied.
7. If anything differs from review, restore the backed-up gateway and sudoers
   independently; do not relax GitHub Actions deployment or database integrity gates.

Because \`prp-diagnose\` uses the file's modification time, a log older than two hours
will report \`STALE_DIAGNOSTIC\` instead of misattributing an old failure to a new run.

## How AI can troubleshoot after setup

1. Open the failed **Deploy PRP** GitHub Actions run.
2. Read its \`PRP production deployment diagnosis (sanitized)\` Step Summary.
3. Open its \`prp-safe-deployment-diagnosis\` artifact if structured details are needed.
4. Correlate \`code\`, \`stage\`, \`table\`, \`production.commit\`,
   \`production.schema_version\` and \`production.service\` against the intended SHA.
5. If \`code\` is unknown, stale, or malformed, ask the authorized administrator for
   a *specific* root-only traceback excerpt. Never guess an unobserved assertion.

## Deployment safety and current V18 blocker

The production V18 rollout remains blocked by its data-preservation preflight, so
**merging this PR would trigger the existing automatic deploy workflow again**.
Keep this feature PR unmerged until there is an approved way to prevent an
unintended V18 retry or the underlying preservation fault is resolved. No root
controller modifications, schema changes, or failed-release retries are performed
by this diagnostic feature itself.

This feature does not disable row fingerprint assertions, migrations, rollback
safety, controller attestation, release identity verification, or production approval.
