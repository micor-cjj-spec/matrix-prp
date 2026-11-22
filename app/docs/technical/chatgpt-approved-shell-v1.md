# PRP ChatGPT-approved remote shell — design and first implementation slice

Status: **DRAFT / DISABLED / NO LIVE SERVER ACCESS**. This branch adds a non-root,
replay-resistant *executor prototype* and offline tests. It does **not** add an
enabled MCP tool, a production workflow dispatch endpoint, an SSH identity or
server installation. It must not be merged or deployed as a working remote shell.

## Desired user experience

1. The owner asks ChatGPT to operate the PRP server.
2. prp_shell_prepare(command, target, timeout) creates a durable,
   owner-bound, immutable draft. There is **no command allowlist**.
3. An MCP Apps approval card shows the **exact unabridged command**, target,
   unprivileged execution identity, timeout, blast-radius warning and a digest.
   If any field cannot be rendered completely, **approval is disabled**.
4. The human physically clicks Approve or Reject in ChatGPT. The UI
   invokes an app-only tool, *not* a model-visible approval parameter.
   Backend rechecks OAuth principal, ChatGPT client, fresh owner grant,
   draft ownership, expiry, and digest. It atomically records the decision.
5. prp_shell_dispatch(draftId) may dispatch **only an APPROVED draft**,
   using an atomic one-time claim. It cannot create or approve drafts.
   A network timeout after dispatch must be DISPATCH_UNCERTAIN, never retried
   automatically (the command might already have run).
6. A GitHub-hosted runner receives **only the job UUID**, not a raw command.
   It retrieves the signed, immutable, *already approved* job over TLS from
   the PRP backend via a dedicated authentication channel. The SSH transport
   accepts only a sealed ticket, and has no access to the signing key.
7. A **separate** root-owned verification gateway checks the HMAC,
   target/owner, issue/expiry window, timeout and nonce. A root-owned atomic
   replay database is committed BEFORE execution. It then switches to a
   dedicated non-root prp-shell account and runs the precise command.
8. The runner returns bounded output privately to PRP. ChatGPT can read the
   owner-scoped status/result, including stdout/stderr, exit code, timeout and
   truncation markers. Raw output **must not** be written to public Actions
   logs, summaries, issue comments, pull requests or artifacts.

## Scope of this first code slice

- app/deploy/chat-shell/prp_shell_executor.py: stdlib-only signed-ticket verifier,
  expiry/target validator, root-only replay ledger, Linux privilege drop and
  bounded command execution. Timeout <= 30 seconds, command <= 8192 UTF-8
  bytes, output <= 16 KiB per stream.
- app/deploy/chat-shell/test_prp_shell_executor.py: offline regressions for
  arbitrary shell syntax, tampering, retargeting, approval spoofing, replays,
  expiry, identity and invocation restrictions.
- .github/workflows/chat-shell-contract.yml: CI-only tests; **NO PRODUCTION
  SECRETS OR SSH**.

No server installer, no sudoers mutation, no root-command mode and no changes
to the existing prp-deploy/prp-inspect identities.

## Signed ticket contract (future PRP backend)

The backend signs the exact UTF-8 JSON job with a 32-byte HMAC key and sends:

    {"ticket":"base64url(raw UTF-8 JSON without padding)","mac":"64 lowercase hex chars"}

Signature: HMAC-SHA256(key, raw decoded ticket bytes).

Signed JSON contains exactly:
- jobId: canonical UUID
- ownerId: positive integer
- target: prp-production
- command: full shell script
- issuedAt / expiresAt: Unix seconds; lifetime <= 5 minutes
- runSeconds: integer 1 through 30
- nonce: 32 through 64 lowercase hexadecimal characters

The backend MUST sign only after persistent independently validated owner
approval and atomic dispatch claim. Runner MUST NOT request new signatures for
arbitrary scripts or retry uncertain dispatches. The host replay database
atomically claims job and nonce before launching a command.

**Signing-key isolation** is essential: the backend may read the key to sign,
but GitHub Actions, the SSH account and the executed command must NEVER read
it. Host verifier uses a root-only 32-byte key at
/etc/matrix-prp-chat-shell.key (mode 0400). Root-only replay directory
/var/lib/matrix-prp-chat-shell has mode 0700. The dedicated SSH identity's
authorized_keys forced command must invoke only the reviewed verifier via an
exact-command sudoers grant; NEVER grant unrestricted sudo.

## ChatGPT approval caveat

The existing health MCP Apps UI demonstrates _meta.ui.visibility=["app"].
That client hint alone is not cryptographic proof of a human gesture.
Before production, independently confirm the ChatGPT host guarantees model
non-invocation of the app-only approval action; if not, enforce a trusted
step-up user verification mechanism within the chat approval experience.

A plain chat message saying “批准” MUST NOT itself set an approval bit.
A model must not pass approved=true, modify the command after display, or use
ordinary PRP write scopes to obtain shell authorization.

## Next implementation units (not completed)

- Backend: isolated durable shell job table, immutable command, owner/client
  binding, atomic approval + dispatch transitions, audit, revocation.
- MCP: model tools prepare/dispatch/status/result, separate app-only decision
  tool, independent prp.shell.* OAuth scopes, default-OFF shell-enabled flag
  and administrator-only owner grant.
- UI: ChatGPT embedded approval card rendering the full command with target,
  timeout, digest, expiry and reject action.
- GitHub: independent workflow, workflow_dispatch only from protected main,
  contents: read permission, isolated environment and SSH key, host-key pinning,
  task UUID as its only input (never raw command or output in public logs).
- Runner: authenticated ticket retrieval, SSH transport and private result
  callback, bounded output, fail-closed uncertain status.
- Server bootstrap: independent root-owned verifier and dedicated non-root
  execution account. Existing deploy gateway and attestor stay unchanged.
- Acceptance: staging first. Verify cross-account rejection, forged approvals,
  revoked grants, command changes, stale tickets, nonces/replay, race,
  command syntax, output limits, live iPhone ChatGPT card and GitHub run
  correlation. No production activation without all checks passing.

## Running offline tests

    python3 -m unittest discover -s app/deploy/chat-shell -p 'test_*.py' -v

Passing these tests proves only local executor protocol, not GitHub connectivity,
ChatGPT human-gesture authenticity, real SSH permissions or production readiness.

## Risk boundary

“Arbitrary command” is possible within the dedicated Linux account's
permissions. There is no implicit root privilege. Privileged mode is a
separate approval and security design. Never publish signing keys, raw shell
commands, stdout or stderr in GitHub Actions logs, artifacts or public issues.
