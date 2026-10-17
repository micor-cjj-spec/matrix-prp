# V19 recovery: live SSH policy attestor prerequisite

Status: **NOT COMPLETE. Production remains V17.** This change prepares one protected
helper upgrade for explicit administrator authorization. It does not install it,
change a production baseline, merge PR #67, enable automatic publishing or publish V19.
PR #62 / V20 is out of scope.

## Evidence and root causes

Rechecked against main `aa273991e38d9f65b89a00adfffe1e3f146ab21a`:

- Production is release `r38606951415-1`, application `79f569e7e668b200a0fa34aa8302cc8db281dea9`, Flyway V17, active.
- Installed controller SHA256 is `7d23ea686b7eca6e66619979357953a0a18fc366d4896f900ea6cae743b396d1`, matching the existing approved manifest. Never replace it with repository server-release.py, which is not byte-identical.
- Installed diagnose helper is root:root 755, SHA256 `bc4ba21b4efaa40efe149f9a36a553af462bb860d1dbe6b53d03abb5b735588c`. It emits only seven legacy diagnostic fields, with no live policy proof.
- Runs 38881218815 and new read-only run 38930427295 both show ordinary command denials and local/remote forwarding denials passing. SFTP INIT sends nine bytes and keeps stdin open: authenticated public-key connection, subsystem accepted, exit 2, zero stdout, no VERSION and no gateway stderr. This is `SUBSYSTEM_EXITED_WITHOUT_VERSION`, not by itself a security acceptance.
- The current production Verifier requires a gateway denial marker for a subsystem request. Its mismatch is the immediate SSH gate blocker. PR #67 correctly refuses to infer permission from EOF, timeout or arbitrary exit but has no installed live attestor or approved policy baseline.
- Run 38880899377 is successful **build only**, publish skipped by the manual-only production guard. This is not evidence of deployment.
- The previous V18/V19 preservation problem concerned historical chat fingerprints. The approved installed controller now compares every historical primary-key row digest; permits only an empty V18 metadata table and exact same-owner durable-key V19 backfill. Those protections remain unchanged. Actual restored-database preflight and production migration are still required after SSH acceptance, not replaced by this code review.

The current SSH policy files predate the listener process, active configuration has
no Match blocks, and root journal authentication entries use `_UID=0` and the
sshd-session executable. These were read-only observations, not a reusable proof.

## One-file implementation and threat model

`build_policy_helper.py` concatenates the unchanged legacy classifier and
`live_policy_attestor.py`, replacing only the legacy Python entry point. The output
is a single root-owned `/usr/local/sbin/prp-diagnose` program with `python3 -I`.

- No arguments. EOF retains legacy seven-field JSON. Exactly 32 bytes followed by EOF request a proof. Extra, partial or held-open input fails with bounded time.
- Derive the SSH ancestor process chain and unique established socket from kernel procfs. Never trust caller-provided SSH_CONNECTION, username, path, config option or environment as evidence.
- Correlate the socket peer and kernel ancestor PID to a root-owned sshd-session journal public-key authentication record, boot ID, process birth and the sole exact restricted ED25519 key. No alternative key file, key command or certificate authority is accepted.
- Check root-controlled file/parent/symlink paths, gateway, helper, binaries, interpreter/modules, authorization and sudo policy. Hash only fixed reviewed sources. Never emit raw keys, IPs, arguments, logs, configs or personal rows.
- For loaded-policy evidence, check the running binary identity and supported listener argv. Require every configuration file and Include-glob directory ctime to precede the daemon's saved systemd realtime start and kernel start. Detect clock-generation disagreement. Configuration changes/reloads that cannot meet this strict bound are rejected, not guessed successful. No reload/restart is performed.
- Compute sshd -T using the kernel socket context. This initial collector intentionally supports OpenSSH 10.0p2, default daemon arguments, global config only, fixed external sftp mapping, no system sshrc and no chroot. Unsupported versions, Match policies, journaling, timing or layouts fail closed and require separate review.
- Re-read trusted records and daemon/authentication process identity before returning; bound subprocess time/output and total collection time. The three booleans derive from runtime checks, not manifest values or cached JSON.

This assumes a trusted root/OS/kernel/systemd journal. It does not claim to defend
against malicious root or a compromised SSH host key. StrictHostKeyChecking and
the existing restricted deployment identity remain mandatory.

## Client separation and approval sequence

This prerequisite PR does not change production SSH acceptance. A main-only,
manual read-only workflow can collect a **candidate**, explicitly marked
`approved=false`, `production_gate_passed=false`. Candidate collection never
populates controller-manifest.json or permits deployment. Existing main CI builds
candidates only; main's production publisher remains manual-only.

The corresponding PR #67 follow-up re-collects proofs using three independent
nonces: before SFTP probes, after them, and after forwarding tests. It checks the
approved baseline every time. A cached proof cannot stand in for re-observation.
The exact exec INIT rejection and real subsystem INIT remain independent, bounded
measurements. Both must meet the complete policy contract; VERSION/payload,
authentication/transport errors, EOF-only uncertainty, timeout or drift never pass.

Sequence:

1. Review this helper code, generated diff, hash and rollback commands. Run full CI.
2. Explicitly authorize only the one-file helper upgrade. No controller/sshd/sudoers/key/gateway changes are requested.
3. Merge the diagnostics-only prerequisite after CI and install the exact approved helper. EOF compatibility and unchanged protected files/service must be verified.
4. Run existing main-only read-only acceptance workflow using environment Secrets. Independently review the candidate hashes against administrator read-only measurements, then approve the exact policy baseline in a separate reviewed manifest change.
5. Finish/review PR #67 with post-probe recollection tests. Run real SSH/SFTP/forwarding acceptance. Do not mark fixture tests as production evidence.
6. Only after all safety gates pass: approved controller backup + restored V17-to-V19 rehearsal, full historical row/content fingerprint comparison, formal V19 publish and actual business acceptance. V20 is not included.
7. Restore automatic publishing only through a separate reviewed workflow change after these prerequisites are proven. Never replace it with `continue-on-error`, a constant success response or a missing-check default.

## Prepared install and rollback commands (NOT executed)

On the reviewed checkout, generate the exact candidate:

```bash
python3 app/deploy/build_policy_helper.py /secure/review/prp-diagnose.candidate.py
sha256sum /secure/review/prp-diagnose.candidate.py
```

Administrator-only precheck, without changing files:

```bash
sudo python3 -I app/deploy/admin_upgrade_policy_helper.py check \
  --candidate /secure/review/prp-diagnose.candidate.py
```

Only after explicit authorization, replace REVIEWED_SHA256 with the separately
reviewed candidate digest:

```bash
sudo python3 -I app/deploy/admin_upgrade_policy_helper.py apply \
  --candidate /secure/review/prp-diagnose.candidate.py \
  --approved-sha256 REVIEWED_SHA256
```

The installer checks the exact existing controller/helper hashes, serializes with
the existing deployment lock, retains root:root 755, creates root-only backups
under `/var/backups/prp-policy-attestor/<timestamp>`, replaces one file atomically
and verifies legacy EOF compatibility and unchanged protected files/service PID.
If the post-install check fails it restores the helper; it never restarts services.

To revert that one helper using the recorded timestamp ID:

```bash
sudo python3 -I app/deploy/admin_upgrade_policy_helper.py rollback \
  --backup-id YYYYMMDDTHHMMSSZ
```

Rollback refuses unexpected current or backup hashes. It restores only diagnose;
the new client remains fail-closed because the old helper lacks a policy proof.

Risks: unsupported policy/layout or clock generation can block deployment;
bounded read-only proof collection adds authentication/journal I/O. No application
traffic interruption, database mutation or permission expansion is designed.
Current production success has **not** been claimed.

## Production boot-identity incompatibility (follow-up)

The approved first helper was installed as SHA256
`8c2f3dc6f3fbe765e106f7e8ce3c1650d453200893b2b0e693e367d6353d8e14`,
with verified rollback backup `/var/backups/prp-policy-attestor/20261017T002707Z`.
Read-only run 38986811841 fails with `SSH_AUTHENTICATION_UNPROVEN`.
Root read-only checks independently show: recent authentication journal boot IDs
are stable but differ from current procfs boot ID; the current administrator SSH
connection shows the same discrepancy. The precise reason for that environment
inconsistency is not established. No reboot or journal restart is proposed.

This follow-up retains a strict journal boot-ID check, anchoring its expected
value to the **current master daemon's trusted startup record**, rather than
assuming that journal and procfs have the same cached boot identity. That record
must have root UID, sshd executable, the live master PID, ssh.service, the current
systemd InvocationID, a valid boot ID, and monotonic timestamp within two seconds
of kernel process birth. Conflicting boot identities or missing startup records
fail closed. Production has two such startup records within 60ms of master birth;
recent auth records carry the same current InvocationID.

Authentication still requires exact ancestor PID, root UID/executable/unit,
peer endpoint, public-key fingerprint, realtime bounds and the anchored boot ID.
It now additionally requires current InvocationID and a monotonic timestamp after
that ancestor's birth and before collection. Master PID, InvocationID and current
kernel boot identity are rechecked at the end. Loaded-policy/clock checks remain.
Old, missing, conflicting or cross-service-generation records never pass.
The full cause of kernel/journal boot-ID discrepancy remains an operational risk;
this mechanism explicitly proves the live daemon generation without guessing.

No new helper installation is performed by this follow-up PR. A changed helper
hash requires fresh explicit approval; the administrator installer expects the
currently installed first helper and backs it up for one-file rollback. The old
installer and original backup remain available for reverting all the way to the
legacy diagnostic. No SSH, sudoers, controller, database or service change.
