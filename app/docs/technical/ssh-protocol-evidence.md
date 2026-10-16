# SSH protocol evidence before changing acceptance rules

The 2026-10-16 production gate stopped at `sftp-subsystem-denial /
EXPECTED_GATEWAY_DENIAL_MISSING`. That proves the old predicate failed, but does
not establish the remote exit status, protocol error, or whether SFTP started.

`ssh host sftp` sends an SSH exec request with a command string. `ssh -s host
sftp` sends a subsystem request. A server can reject the latter before the forced
gateway executes, so requiring a gateway message for both needs live evidence.

This evidence PR deliberately leaves `verify_ssh_boundary.py` acceptance unchanged.
An OpenSSH subsystem marker is recorded, not silently promoted to a production
PASS. After live evidence establishes the exact result, a separate reviewed fix
can recognize an unambiguous protocol rejection while continuing to reject
authentication, host key, transport, timeout, payload and unknown errors.

## Read-only workflow

`PRP read-only SSH acceptance` is manual-only, main-only, uses the existing
`production` environment secrets, shares the production concurrency lock, and has
no backup, database, application switch or deployment step. It runs the checked-out
commit's probe. The probe sends only the existing controller hash/diagnose commands,
harmless denial requests, and loopback port 1 forwarding tests. No test requests
business data or writes application records. Every SSH call has a 20 second limit.

The JSON summary/artifact contains fixed stage names, numeric exit status and
stdout byte count, stdout emptiness, boolean denial/protocol markers and enumerated
exceptions. Remote output and exception text are never logged or uploaded.
After a failure beyond controller attestation and diagnostic validation, the probe
still measures both forwarding boundaries. Production acceptance remains fail-fast.
The probe exits nonzero if any existing acceptance rule fails; evidence collection
does not grant deployment authorization.

Ordinary forwarding permission denials must match their specific protocol markers
and exit code, with no stdout. Authentication/network/host-key errors and timeouts
remain failures even if accompanied by a rejection marker. If a wrongly permitted
remote forward starts, its SSH connection times out and disconnecting removes the
ephemeral listener. There is no application payload and the target is loopback port 1.

## Merge safety and current authorization limit

Main CI now automatically builds **candidates only**. The production publish job
requires an explicit manual dispatch, and the dispatch default is `build`. Thus
merging diagnostics cannot automatically execute production migrations. Existing
artifact provenance, controller attestation, SSH gate and data protection are retained.
Manual deploy/promote requires separate human authorization; a successful read-only
probe is not authorization to publish.

At preparation time, production environment branch policy allows only `main`.
Therefore a PR branch cannot run this workflow with production credentials. Do not
change that policy, expose secrets to PRs, add another key, or use a different
workflow as a secret-access workaround. With authorization limited to preparing a
PR, live protocol results remain unverified. After separately authorizing this PR's
merge (which is build-only), dispatch `ssh-readonly-acceptance.yml` on main and inspect
the `prp-readonly-ssh-evidence` artifact / Step Summary. Do not dispatch Deploy PRP.

Tests cover protocol denial telemetry without premature acceptance, successful or
interactive SFTP fail-closed behavior, connection and timeout errors, forwarding
permission checks, redaction, workflow isolation, and automatic-publish prevention.
