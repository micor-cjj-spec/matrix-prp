# V1.1 sandbox installation review (not an installation script)

Offline candidate only. No actual server changes, enabling, permissions or deployment authorized. The production V1 channel stays disabled. Do not run these checks against production resources. No new package install or systemd changes without separate approval.

## Selected candidate

A dedicated non-root staging worker in a bounded systemd cgroup uses rootless Bubblewrap with a separately provisioned minimal, immutable root filesystem. No host-shell fallback. Rootfs contains only reviewed Bash/Python runtime, libraries and empty mountpoints. It is not a copy or bind mount of the host operating system. No production/staging credentials, SSH keys, Docker socket, host config, application mounts, privileged device, package installer credentials or network dependencies. Bind only the verified per-job input folder read-only; /tmp is disposable, with the dedicated memory limit. Script output is bounded, not printed by the bridge; output must be encrypted and authenticated before transmission.

Candidate fixed paths:
- /opt/matrix-prp-remote-executor-v11/rootfs
- /etc/matrix-prp-remote-executor-v11/sandbox.enabled (absent by default; root-owned mode 0444)
- /system.slice/prp-remote-executor-v11.service (dedicated cgroup v2)
- /usr/bin/bwrap and /usr/bin/prlimit (trusted non-setuid binaries)

Installation review must validate the exact Bubblewrap version and supported flags, user namespace support and existing AppArmor/SELinux policy. Do not disable host security policies to make the launcher work. If unavailable, use a separate disposable VM / isolated hosted CI instead. Preflight verifies non-root identity, root-owned immutable runtime paths, gate content, non-setuid launchers, no nested rootfs mounts, NoNewPrivs, empty effective and bounding capabilities and dedicated cgroup v2 limits. It cannot establish rootfs provenance or all kernel isolation properties; prove those separately.

Expected service limits: MemoryMax <=512 MiB, MemorySwapMax=0, TasksMax <=64, CPUQuota <=100%, NoNewPrivileges=yes, empty CapabilityBoundingSet. No root, sudo, Docker group, shared production data or credentials. Separate transport and execution identities if the transport requires networking; never give script access to SSH secrets. Evaluate service read/write protection, file ownership, storage quota and actual process cleanup. The worker is not a general root or staging mutation handler. All live paths are candidates until independent acceptance.

## Required real acceptance before activation

1. Exact-head CI plus independent code/security review. Inventory rootfs digest, packages, mountpoints, permissions and trusted binaries; verify no host filesystem or secret leakage. Confirm capacity with other stage tasks.
2. On a disposable isolated instance only, run harmless Bash/Python smoke, verify input digest and read-only input, temporary-file behavior, interpreter and arguments. Assert host files, host network, production sockets, other jobs, host devices, nested user namespaces and credentials are inaccessible. Verify that inability to create namespaces prevents launch rather than falling back.
3. Verify timeout and forked/daemonized descendant cleanup with actual cgroup/PID namespace evidence. Current adapter deliberately records RECONCILE_REQUIRED on timeout even after outer launcher termination. Do not certify cleanup from exit status alone. Prove resource limits under bounded test; no load testing on the shared production host.
4. Verify task data quota, TTL, recovery of uncertain state, cancellation, transfer interruption, one-time claim, replay prevention and concurrent stage operation lock. These are not all implemented yet.
5. Verify encrypted/signed status/result including cross-chat retrieval. Review independent owner-comment approval risk. Verify no raw outputs or secrets in public GitHub.
6. Only then separately approve a one-time staging initialization, explicit default-off gate activation and harmless live E2E. Any stage mutation uses a separately authorized typed handler and existing staging mutex. No arbitrary root/Docker commands. Preserve production hold, other tasks and V1 gate.

No deployment scripts or systemd unit are supplied by this checkpoint. A successful mock or CI test is not proof of actual Linux isolation or host readiness.
