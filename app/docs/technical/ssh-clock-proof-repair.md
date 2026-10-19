# SSH policy proof: stable daemon generation across wall-clock adjustment

## Observed failure

Main f0c0df0ee6b7c85bef68389cfe6c351a66090dc3 builds successfully but release
39195467311 stops before production operations. Read-only run 39209589477 exports
SSH_CLOCK_GENERATION_UNPROVEN. The saved systemd realtime birth and today's
wall/boot-derived estimate differ by about 0.519 seconds after about 128800 seconds
uptime, exceeding the old fixed 0.1 second check. Systemd and kernel monotonic birth
agree to about 25 microseconds. NTP is enabled/synchronized; the exact historical
clock event is not inferred from these snapshots alone.

## Minimal runtime change

Only `daemon_birth()` changes in the installed, self-contained diagnostic helper.
The original seven-field log reader, session/socket/public-key/journal anchoring,
root trust checks, source inventories, configuration ctime guard, output/time
limits and three nonce-bound client recollections remain unchanged.

The replacement checks both systemd's saved realtime and monotonic start values.
The monotonic value must agree with the live kernel start tick within the original
0.1 second generation allowance. Sampling must be bounded; future/zero/malformed
timestamps and suspend/namespace clock-domain offsets fail closed. A bounded
accumulated clock-offset difference (500 ppm of uptime plus 0.1 second sampling
allowance) replaces the invalid assumption that the realtime offset never changes.
Large out-of-envelope discrepancies remain failures. This does not reconstruct
clock history or claim that every possible historical discontinuity is identifiable.

The loaded-config boundary remains `min(saved realtime, conservative current
mapping) - 0.02`. The config ctime comparison is unchanged, so forward wall-clock
movement cannot make a newer config pass. Missing/new files, changed Include
directories, unknown generation and baseline drift remain refusals. Master PID,
binary, InvocationID and boot/journal generation are still independently checked.

References: [systemd timestamp properties](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html),
[Linux clock adjustment limits](https://man7.org/linux/man-pages/man2/adjtimex.2.html).

## Exact one-file repair procedure

Installed helper expected SHA256:
9070861e69b3ec2a0106f3e6c9992f3344397eecccd9cc80e42370392517121f.
Deterministically bundled candidate SHA256:
84343877e8510ebe6722849867e989c234a55805128eaa8f166816e74d0f8483.
The controller remains c329836ed2f48296e5ab505451aab3c59b33db7f7c20aba5ae7c2b1ec80622e2.

The administrator installer pins these old helper/controller identities, requires
an exact approved candidate digest, and rejects every AST change except the single
daemon_birth function. It holds the deployment lock, validates root:root 0755,
backs up/verifies old bytes, replaces atomically with fsync and verifies legacy EOF
compatibility and unchanged protected files/service state. Failure restores old
helper bytes. No SSH/app service restart, SQL operation or permission expansion.

```bash
python3 -I app/deploy/admin_upgrade_policy_helper.py check --candidate /root/prp-clock-review-20261019/prp-diagnose.candidate.py
python3 -I app/deploy/admin_upgrade_policy_helper.py apply --candidate /root/prp-clock-review-20261019/prp-diagnose.candidate.py --approved-sha256 84343877e8510ebe6722849867e989c234a55805128eaa8f166816e74d0f8483
# To restore only the diagnostic helper, use the receipt's actual backup ID:
python3 -I app/deploy/admin_upgrade_policy_helper.py rollback --backup-id YYYYMMDDTHHMMSSZ
```

Independent root inventory must match the currently approved baseline BEFORE
repair. After replacement, independently remeasure it and review that only the
helper record changed. Approve the exact installed helper and policy-file digests
in the manifest; never copy a candidate proof into approval without comparison.
Even a byte rollback changes ctime and requires a fresh independent policy review.

The repair PR adds publication-hold.json: application publication stays blocked
while the helper/manifest are updated and real read-only SSH acceptance runs.
Keep the hold after repair; deleting it to release the pending application is a
separate operation and is not part of this diagnostic-only repair request.
