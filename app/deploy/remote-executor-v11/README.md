# Remote Executor V1.1 — offline candidate

Reuse #277 / #273 / #296 / #299 CMS and SSH transport; reference #309 / #424 security findings and #396 / #456 regression contract. No activation or deployment authorized.

## Minimal delivery
Separate staging-only protocol namespace, SSH identity, certificate, ledger and environment. Do not enable or modify the production V1 channel. Reuse existing cryptographic primitives, pinned host verification and safe diagnostic labels. Owner comment is not independent cryptographic proof of chat approval; document residual risk before activation.

Proposed exclusive paths:
- app/deploy/remote-executor-v11/README.md
- app/deploy/remote-executor-v11/protocol.py
- app/deploy/remote-executor-v11/bridge.py
- app/deploy/remote-executor-v11/executor.py
- app/deploy/remote-executor-v11/test_executor.py
- app/deploy/remote-executor-v11/install-review.md
- .github/workflows/remote-executor-v11-contract.yml
- .github/workflows/remote-executor-v11.yml (default disabled; no live secrets in PR CI)

Use bounded encrypted inline script bytes as initial artifact, exact SHA256, UUID, nonce, expiry and target. Bash/Python only inside isolated nonproduction sandbox with no production mounts, credentials, network access or Docker socket. Fixed staging operations separately mapped to reviewed typed handlers; no caller-supplied privileged shell. Durable claim/status/result, no automatic retry after uncertain execution. Bound CPU/memory/processes/output/time, terminate entire job scope. Encrypt and authenticate result, bind job and artifact hash. No plaintext script/output in public GitHub comments or logs. Initial size limited by existing CMS envelope; larger artifact transport deferred.

Offline tests: digest mismatch, replay, expiry, wrong target, malformed input, wrong actor, output bounds, timeout and descendant cleanup, status authorization, production isolation, fixed operation denial, simulated transport. Existing CI plus independent review. Real isolation and installed identity must be verified before separately approved one-time initialization and harmless end-to-end pilot. #396 S6.2 remains independent; no real business writes. No changes to existing workflows, publication hold, OAuth, or parallel task files. No merge or deployment.
