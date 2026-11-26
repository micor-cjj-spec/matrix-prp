# Remote Executor V1.1 — detailed offline candidate

Status: P1 protocol and P2 offline ledger/spool candidate implemented; tests pending exact-head CI. Reuse #277 / #273 / #296 / #299 CMS and SSH transport; reference #309 / #424 security findings and #396 / #456 regression contract. No activation, new live permission, merge or deployment authorized.

## Objective and delivery scope

ChatGPT prepares a bounded job including command or file manifest, shows the proposed impact and obtains explicit approval for execution and mutations. The existing GitHub connector transmits the approved job; the server receives and verifies files, runs a sandboxed script or a fixed staging handler, and returns authenticated encrypted status/results. Daily operation requires no manual SSH, upload or GitHub UI after a separately authorized one-time installation. The existing production V1 remains disabled.

Historical workload classes: read-only diagnostics, small Python/Bash scripts, multi-file configuration validation, large CI image artifacts (~203 MiB), staging preflight and regression. Shared host root, Docker, ingress and production changes cannot be replaced by an unrestricted script runner.

## Architecture and transport

Separate staging-only protocol namespace, SSH identity, recipient certificate, result signing identity, ledger and environment. Reuse existing CMS, pinned host verification and safe diagnostic labels. Fixed owner-only issue_comment entry and trusted default-branch workflow, never pull_request code with live credentials. No new public HTTP listener or self-hosted GitHub runner on shared host. No production V1 gate modification. GitHub owner identity is not independent cryptographic proof of chat approval; document and accept residual risk explicitly before activation. Trust only verified owner-created events, bound to exact request, expiry and nonce.

Three file sources:
1. Bounded encrypted inline envelope for small scripts/configuration; conservative 8 KiB total file payload initially, subject to measured CMS/comment overhead. Multiple files with manifest; no plaintext on public GitHub. Chunking may be considered only after measured connector limits and quotas.
2. Immutable repository file at exact commit and path (non-sensitive source already in repository); verify SHA256 and size. Never resolve moving branch at execution.
3. Existing GitHub Actions artifact from a trusted producer, bound to repository, workflow, successful run ID, exact source SHA, artifact ID, name, size and SHA256. Download on trusted hosted runner and stream over the dedicated SSH channel into a staging spool. Verify outer archive and inner file manifest; no arbitrary URL or user-selected credential target. Initial proposed large transfer ceiling 512 MiB, only after disk/capacity tests and approval. Use resumable transfer by bounded verified chunks if necessary; no execution until all bytes verified. Never place binary images, confidential input or unencrypted logs in the public repository.

For arbitrary large local/chat attachments that are not already available from a trusted CI artifact, the existing connector exposes no verified general attachment upload API. Do not promise zero-click upload for these files. Design an optional private artifact provider/upload adapter only if needed, with separate authorization and connector capability verification; prefer rebuilding repository-derived artifacts in CI. Do not require manual upload for normal CI-generated artifacts. No arbitrary outbound URLs.

## Job contract and approval

Job UUID, protocol version, staging target, operation enum, task/issue reference, immutable file manifest (relative paths, bytes, SHA256, source IDs), entrypoint/interpreter, typed args, bounded limits, expiry, nonce and response certificate. Canonical manifest digest includes operation, target, artifact IDs/digests, arguments and limits; approval is for this exact digest and target. Any change needs renewed approval. Transfer-only is also a separately bounded action; scripts cannot be executed merely because upload succeeded. Distinguish fixed read-only operations (within explicit existing authorization), sandbox execution, and fixed staging mutations. No permission for arbitrary production or privileged shell, sudo or Docker socket. Existing test/business-write approvals still apply.

## Execution

Receive into per-job private spool, enforce disk quota and file count/size, reject traversal, absolute paths, symlinks, devices, duplicate paths and archive expansion bombs; write atomically and verify hashes before readiness. Never write to /root or live application paths. Script sandbox: separate non-root identity, no host/prod mounts or secrets, no Docker socket, no network by default, bounded CPU/memory/PIDs/time/output, whole scope descendant cleanup, no privilege escalation. Real boundary requires host verification; if isolation cannot be proven, run on separate disposable VM or hosted CI only.

Staging-specific operations use separate reviewed, fixed typed handlers or existing authorized runner interfaces. Initial handlers: staging health/preflight and artifact inspection; image import, stage restart or route updates remain disabled until an exact target, reviewed handler, backup/rollback and authorization are available. Shared Nginx changes are not general sandbox operations. Never pass caller scripts or arbitrary parameters to root/sudo/Docker. Reuse #396 runner and existing staging mutual exclusion; do not run business CRUD without its own approval. Stage-only mutations acquire existing shared lock and fail closed on contention.

## Status and results

Durable state machine RECEIVED -> TRANSFERRING -> VERIFIED -> QUEUED -> RUNNING -> SUCCEEDED/FAILED/TIMED_OUT/CANCELLED; separate REJECTED and UNKNOWN/RECONCILE_REQUIRED. Claim UUID/nonce transactionally before side effects. Resume transfer by manifest; never automatically replay uncertain execution. Read status without re-executing. Provide job ID, timestamps, digest, exit status, bounded sanitized stdout/stderr, result artifact manifest and authenticated receipt; encrypted payload to public issue only. Sign response with pinned server identity; bind receipt to job, manifest and request. Durable server result can be retrieved in a later authorized chat with a fresh response certificate; do not depend on a previous ephemeral private key. Status/results scoped to authorized owner/job, no public plaintext or secrets. Cancellation cooperative/whole scope, does not imply rollback.

## One-time installation and acceptance

Separate staging account/forced command/key/cert and root-owned configuration, dedicated nonprivileged spool and sandbox, trusted workflow default-branch activation and staging-only credentials; no general root/Docker privileges. Preserve revoke/disable switch and independent production hold. Install only after exact-head CI and independent review and separate approval; verify no prod routes, mounts, credentials or identity sharing. Proposed limits: one concurrent mutation; sandbox concurrency initially one; 8 KiB inline, 512 MiB large artifact, bounded 64 KiB result with measured encrypted transport chunks, per-job disk/TTL and timeout to be confirmed with capacity. No additional governance service, database or UI; local SQLite ledger and existing GitHub connector are sufficient.

E2E acceptance: harmless Bash/Python, multi-file upload with SHA256, trusted CI artifact >=203 MiB transfer and verification, staging read-only check, status from new chat, duplicate/expired/rejected/timeout and descendant cleanup, interrupted transfer recovery, no production access. Fixed staging mutation tested separately only with existing scope and approval. Negative cases: wrong actor, wrong target, tampered digest/signature, path traversal, unsafe archive, quota, arbitrary URL, unexpected source, lock contention, unauthorized status, production mount/network and credential leakage. CI green is not live validation.

## Exclusive candidate paths (eight; scope changes only after coordination)

- app/deploy/remote-executor-v11/README.md
- app/deploy/remote-executor-v11/protocol.py
- app/deploy/remote-executor-v11/bridge.py
- app/deploy/remote-executor-v11/executor.py
- app/deploy/remote-executor-v11/test_executor.py
- app/deploy/remote-executor-v11/install-review.md
- .github/workflows/remote-executor-v11-contract.yml
- .github/workflows/remote-executor-v11.yml (default disabled; no live secrets in PR CI)

Implementation order: P1 immutable manifest/inline and CI artifact contract; P2 sandbox/ledger/status; P3 trusted bridge and streamed CI artifact; P4 offline and complete CI plus independent code review; P5 separately authorized initialization and E2E. No changes to other tasks, production publication hold, existing workflows, OAuth or Keycloak. No merge/deployment without explicit separate approval.

## Implementation checkpoint P2

The internal Ledger provides durable SQLite job/nonce claim, private per-job files, bounded streaming with SHA256 verification, atomic file publication, preclaim re-verification, single active/uncertain job, pending cancellation, persistent status and bounded result. It contains no process launcher or network interface. Interrupted transfer restarts a single file from byte zero; true chunk resume remains P3. No actual shell, Python, SSH, or staging operation runs. The caller must authenticate, bind approval and provide a validated isolation adapter; the manifest digest is not an authentication credential. Remaining live blockers include cumulative disk quota/TTL/cleanup, trusted spool ownership and separate sandbox identity, transport deadlines, host resource isolation, result signing, stage mutex integration, and explicit uncertain-state reconciliation. Offline tests use temporary local storage and synthetic result records. No live server activation.
