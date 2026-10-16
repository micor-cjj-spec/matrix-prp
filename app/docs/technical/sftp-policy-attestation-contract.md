# SFTP forced-gateway correlation: blocked pending live server policy proof

## Status and authorization

The client implementation is deliberately fail-closed and not production-ready:
production has neither an approved SSH-policy baseline in controller-manifest.json
nor a policy proof supplied by its current root diagnostic helper. A historical
administrator inspection and an exec refusal cannot detect future policy drift.
Do not merge this client-only change to claim a successful production gate.

No production SSH configuration, authorized_keys, sudoers, gateway, controller,
database or application is modified. Automatic production publishing remains off.
The existing main-only read-only workflow is unchanged. No deployment is authorized.

## Client decision, exercised by the actual production Verifier

1. Verify controller SHA256, safe diagnostic JSON, ordinary shell/command/argument/
   injection denials through the pinned host and restricted identity.
2. Require an independently reviewed approved_ssh_policy baseline. It contains
   hashes of the gateway, authorized_keys, canonical effective sshd configuration,
   canonical policy-file metadata/content and the policy attestor itself, plus
   exact deployment-key fingerprint, forced command, subsystem mapping and the
   confirmed OpenSSH 10.0 stderr-ignore behavior identifier. No default baseline.
3. Generate a fresh cryptographic 32-byte nonce and call the existing literal
   diagnose command with that nonce on stdin. Require its normal strict diagnostic
   response plus one ssh_policy object. Reject duplicate/unknown fields, stale
   proofs, wrong nonce, unverified runtime policy or any baseline mismatch.
4. Through the same SSH destination/identity, send INIT-only to an exec request for
   the exact attested /usr/lib/openssh/sftp-server command. Require explicit gateway
   denial, exit 2, zero stdout and no VERSION, with positive public-key authentication.
5. Independently send INIT-only to the actual subsystem request, holding stdin open.
   Require exit 2, request accepted, zero stdout, no VERSION or other response,
   positive public-key authentication and only the verified forced-gateway outcome.
6. Reject auth/host-key/network failures, timeout, output limits, incomplete evidence
   and unknown outcomes at either probe. Recheck proof freshness after both probes.
   Only then return SFTP_DENIED_BY_FORCED_GATEWAY. Continue original forwarding tests.

There is no acceptance path based solely on an exec refusal or exit 2/no stdout.
The special outcome is never enabled by the current production manifest. Other
SSH versions/mappings require a separate review; drift must not update baselines
automatically. A valid VERSION from either INIT probe always blocks.

## Proposed minimal server interface (NOT installed by this PR)

Reuse `/usr/local/sbin/prp-diagnose` and its existing no-argument sudo authorization.
Do not add an SSH command or modify the gateway, sudoers, authorized_keys or sshd.
An independently approved update to that ONE existing root-owned helper would:

- Keep its original 7-field log-only JSON when stdin is EOF (existing consumers).
- For exactly 32 input bytes within a short deadline, compute live read-only policy
  evidence and append the fixed ssh_policy object below. Refuse extra input.
- Accept no file path, username, command, config option or arbitrary shell input.
- Read only fixed reviewed paths, reject unsafe symlinks/permissions, and retain
  root ownership. Bind the connection to the actual authenticated restricted key
  and SSH peer/session, using kernel/process state rather than caller-supplied env.
- Derive the effective Match policy for that connection and verify the loaded
  daemon/config state. `sshd -T` alone describes files on disk, not proof of what
  the running daemon loaded. If this relationship cannot be established, set
  loaded_policy_verified=false and block; do not guess or reload/restart sshd.
- Check all relevant main/include configuration files, authorization sources,
  gateway, interpreter, sshd/sshd-session binaries, SFTP binary, attestor and their
  root-controlled parent paths. Hash canonical content plus path/owner/group/mode
  metadata; verify the single expected restricted key and exact forced mapping.
- Emit only nonce, UTC time, fixed booleans and hashes/identifiers. Never emit public
  key content, environment, raw configs/logs, filesystem data or caught exceptions.
- Bound reads, subprocess time/output and total runtime. Fail closed on collection
  errors, unknown policy, pending/unverifiable reload state or context mismatch.

Normal diagnostic response gains exactly one `ssh_policy` property in proof mode:

```json
{
  "schema_version": 1,
  "challenge": "64 lowercase hexadecimal characters echoing the request nonce",
  "observed_utc": "RFC3339 UTC ending in Z",
  "baseline": {
    "gateway_sha256": "reviewed live SHA256",
    "authorized_keys_sha256": "reviewed live SHA256",
    "effective_sshd_sha256": "canonical effective-policy SHA256",
    "policy_files_sha256": "canonical trusted-file metadata/content SHA256",
    "attestor_sha256": "installed approved helper SHA256",
    "deployment_key_fingerprint": "SHA256:deployment key fingerprint",
    "subsystem_command": "/usr/lib/openssh/sftp-server",
    "forced_command": "/usr/local/bin/prp-deploy-gateway",
    "behavior": "openssh-10.0-subsystem-stderr-ignore"
  },
  "connection_bound": true,
  "loaded_policy_verified": true,
  "trusted_paths": true
}
```

The `baseline` is computed from live state; it must NOT be copied from a previously
saved JSON file. The client compares it to separately reviewed immutable values.
Proof age at the beginning and end must be between -5 and 30 seconds. Changing the
root helper still requires explicit administrator approval and an exact backup,
diff/hash/mode review even though it uses the existing sudo boundary. This task
explicitly prohibits that production-file change, so it has NOT been performed.

No root helper implementation or broad read API is supplied here: loaded-policy
and session binding must be implemented and reviewed against the real server,
not replaced by constant true flags. Until then, leave the PR unmerged, keep FAIL
and retain the running V17 service. Formal V19 publishing requires separate approval.


## Recovery hardening

The verifier now recollects independent nonce-bound proofs after the two SFTP probes and again after forwarding checks. This detects filesystem/policy drift during testing and prevents replaying the pre-probe proof as a post-probe observation. Fixture tests exercise both drift and replay rejection. Production baseline and helper authorization are still prerequisites; no policy values are auto-approved.
