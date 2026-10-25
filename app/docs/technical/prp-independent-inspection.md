# PRP independent, read-only production inspection

## Purpose and boundaries

The ChatGPT GitHub integration can read GitHub Actions results, but it has **no
direct production SSH shell**. This proposal adds an independently provisioned
identity, `prp-inspect`, which can request exactly one fixed report. The report
contains service state, hash matches against the *reviewed repository manifest*,
known deployment-error categories and bounded 10-minute journal **counts**.
Raw application/SSH logs, SQL, private row data, secrets and file contents never
leave the host. The report is diagnostic, **NOT** an SSH policy proof.

This is deliberately separate from the existing `prp-deploy` identity and the
`Deploy PRP` workflow. No production credentials, permissions, server files,
service definitions or databases are modified by this feature PR.

**Current blocker (2026-10-19):** merge commit
`1b79c6ae4e5db86a5e8de6860c598f75f9b334f6` built successfully, but
production publish run 39190199886 failed at
`ssh-policy-attestation / SSH_POLICY_PROOF_UNAVAILABLE`. The new inspector
does not bypass or fix the deployment attestation. No release switch occurred.

## Architecture

```text
Manual, authorized workflow_dispatch on main
   -> GitHub environment: production-inspect (separate secrets/reviewers)
   -> SSH key: prp-inspect only (restrict + forced command)
   -> /usr/local/bin/prp-inspect-gateway
      accepts SSH_ORIGINAL_COMMAND == "report" only
   -> sudo -n /usr/local/sbin/prp-inspect-report (exact no-argument rule)
   -> fixed-path reads of systemd, trusted binary digests, existing
      no-argument prp-diagnose and 100 recent journal lines in memory
   -> fixed-schema JSON (no raw logs/rows/paths/user content)
   -> local strict validator before GitHub output
   -> sanitized Step Summary and 7-day artifact
```

The new SSH key **must not** be a `prp-deploy` key. The new user may use
`/bin/sh` because OpenSSH invokes forced commands using the login shell;
`/usr/sbin/nologin` would break the gateway. Its password is locked and its
sole authorized SSH key is forced to the gateway. No changes to `sshd_config`,
global `Match` rules or existing `authorized_keys` are requested here.

## Stage 0 — Independent review (no production change)

1. Review the complete PR, including `app/deploy/prp_readonly_report.py`,
   `prp-inspect-gateway.sh`, `validate_inspection.py`, and
   `.github/workflows/prp-readonly-inspect.yml`.
2. Wait for all CI checks to pass. Record the reviewed commit SHA and the
   expected SHA256 of both new server files. **Do not trust a GitHub Actions
   artifact as a deployment-authorized server installer.**
3. Plan the policy baseline refresh **before** provisioning. The current
   `live_policy_attestor` includes root-owned sudo policy files in its
   `policy_files_sha256`. Adding `/etc/sudoers.d/prp-inspect` can change the
   approved SSH policy digest; the existing production gate MUST continue to
   fail until independent root measurements and a separately reviewed manifest
   approval reconcile the new policy. **Never copy new values from an untrusted
   candidate directly into the manifest.**
4. Keep a second independent administrator login available and preserve backups
   and rollback instructions. First fix or separately diagnose the existing
   `SSH_POLICY_PROOF_UNAVAILABLE` attestation; don't treat the inspector as
   an attestation replacement.

## Stage 0.5 — Existing installation inventory (read only)

Before proposing any new SSH user, sudoers entry, or GitHub Secret,
an authorized administrator can use their **existing** SSH account to make
the following bounded, no-sudo, no-change inventory on the PRP host.
These checks print only `PRESENT`/`ABSENT`, never passwords, keys,
file contents, command-line arguments, hostnames, or user records.

```sh
if getent passwd prp-inspect >/dev/null; then
  echo 'inspect_account=PRESENT'
else
  echo 'inspect_account=ABSENT'
fi
for item in /usr/local/bin/prp-inspect-gateway \
            /usr/local/sbin/prp-inspect-report \
            /etc/sudoers.d/prp-inspect; do
  case "$item" in
    /usr/local/bin/prp-inspect-gateway) label=inspect_gateway ;;
    /usr/local/sbin/prp-inspect-report) label=inspect_report ;;
    /etc/sudoers.d/prp-inspect) label=inspect_sudo_policy ;;
  esac
  if test -e "$item"; then echo "$label=PRESENT"; else echo "$label=ABSENT"; fi
done
```

A `PRESENT` result is not proof that permissions, hashes, forced-command SSH,
the effective sudoers policy, host-key pinning, or production SSH policy baseline
are correct. It never authorizes running the installer or copying deployment
credentials. If all components are absent, stop and plan the independently
reviewed Stage 1 bootstrap; do not change anything merely to make an Actions
diagnostic green.

The companion GitHub workflow is intentionally `main`-only and protected
by the separate `production-inspect` environment. Before storing any new
inspection secret, configure available human review and branch restrictions
on that environment, and separately reconcile potential global SSH-policy
attestor changes as described below.

## Stage 1 — Administrator-only bootstrap (NOT run by CI)

Use an independently reviewed checkout pinned to the approved PR commit.
The examples below are intentionally manual; a trusted administrator must
inspect the actual host and approve each filesystem/permission change.
Do **not** run remote fetched scripts as root or paste private keys into chat.

Create the account (only if it doesn't exist, after confirming no conflict):

```bash
sudo useradd --system --create-home --home-dir /home/prp-inspect --shell /bin/sh prp-inspect
sudo passwd -l prp-inspect
sudo install -d -o prp-inspect -g prp-inspect -m 0700 /home/prp-inspect/.ssh
```

Generate a **new** dedicated Ed25519 keypair on a trusted administrator device,
not in ChatGPT or public logs. Put its public key into the sole
`/home/prp-inspect/.ssh/authorized_keys` record using this exact structure
(the placeholder is a PUBLIC key, not the private key):

```text
restrict,command="/usr/local/bin/prp-inspect-gateway" ssh-ed25519 <PUBLIC_KEY>
```

Ensure `authorized_keys` belongs to `prp-inspect:prp-inspect`, is mode
`0600`, `.ssh` is `0700`, and there are no other authentication keys.
Do not enable password authentication. Verify the host SSH fingerprint
independently before populating GitHub's `known_hosts` secret.

Review the exact checked-out source before copying these two **new** files;
do not overwrite `prp-release`, `prp-diagnose`, or the existing deployment
gateway:

```bash
sudo install -o root -g root -m 0755 app/deploy/prp_readonly_report.py /usr/local/sbin/prp-inspect-report
sudo install -o root -g root -m 0755 app/deploy/prp-inspect-gateway.sh /usr/local/bin/prp-inspect-gateway
sudo sha256sum /usr/local/sbin/prp-inspect-report /usr/local/bin/prp-inspect-gateway
```

Create only this exact-command sudoers rule in a temporary root-owned file,
validate it with `visudo -cf`, then install it as
`/etc/sudoers.d/prp-inspect` mode `0440`:

```sudoers
prp-inspect ALL=(root) NOPASSWD: /usr/local/sbin/prp-inspect-report ""
```

The trailing `""` is important: **no command arguments** are authorized.
Do not add `NOPASSWD: ALL`, `journalctl`, `cat`, `bash`, `sh`, or sudo
wildcards. Do not grant the inspect user group access to unrestricted journals.

## Stage 2 — Configure the separate GitHub environment

Create the `production-inspect` GitHub Actions environment, restrict it to
`main`, and apply human reviewer protection. Define these **environment**
secrets (not committed to the repository):

- `PRP_INSPECT_HOST` — same target host as production, but separate secret.
- `PRP_INSPECT_SSH_KEY` — dedicated private key, never reused for deployment.
- `PRP_INSPECT_KNOWN_HOSTS` — **verified** host-key line.

Do not remove/change `PRP_DEPLOY_*` credentials, the existing `production`
environment or the deployment workflow.

This integration can **read** GitHub Actions jobs and artifacts; whether it
can **dispatch** a workflow depends on connected GitHub capabilities. With the
currently available GitHub connector, the authorized operator initiates
`PRP independent read-only inspection -> Run workflow -> main`. ChatGPT can
then inspect the sanitized run details via GitHub.

## Stage 3 — Negative tests and acceptance

Before treating the inspector as ready, verify from the **dedicated inspect
identity**:

- `ssh -T -i <INSPECT_KEY> prp-inspect@<HOST> report` returns exactly one
  validated JSON object; no raw logs, file contents, service environment,
  credentials or database records appear.
- Requests for `sh`, `status`, `report --file /etc/shadow`,
  `report; id`, empty commands, SFTP and forwarding all fail. Do not run
  arbitrary shell tests over the deployment identity.
- Existing `prp-deploy` identities, controllers, gate checks and sudoers
  remain unchanged; systemd and database data are unchanged.
- The report can correctly classify deliberate mock failures in isolation;
  unknown data is refused by `validate_inspection.py`.
- Production's independently reviewed SSH policy baseline is updated via
  separate approved change after the administrator verifies host measurements.
  The main production SSH gate still must pass **on its own merits** before
  retrying `Deploy PRP`.

For rollback, revoke the dedicated public key and GitHub inspect secrets
immediately, then under administrative change control remove only the new
account, its two dedicated files and the exact sudoers entry. Independently
remeasure SSH policy digests for the deployment attestor afterward.

## Limits

- Reported file hash matches do not prove the *loaded* sshd policy, current
  session identity, SFTP/forwarding denials, or correctness of a live nonce.
- Journal counters are heuristics over at most 100 lines in the last 10
  minutes; a zero count does **not** prove no errors happened.
- The existing `prp-diagnose` is called with no stdin challenge solely for
  its legacy seven-field error classifier; its policy proof is deliberately
  not requested on the inspect identity.
- This workflow has no deployment, restart, database, rollback, or shell
  capability. The production controller and fail-closed gate stay intact.
