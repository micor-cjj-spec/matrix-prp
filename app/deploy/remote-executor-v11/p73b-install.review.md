# P7.3B connection preparation — review only, not executable installation
Owner Issue #506, exact P7.2 installed source f24896eca0d2016e843b919fbcc7ef6f45521cab. Preserve #277, production hold, and all absent gates. No real keys, SSH changes, unit registration, service start or workflow activation in this PR. The three installed runtime files are unchanged.

## Transport and credentials
Review-only workflow remote-executor-v11.yml.review mirrors #277's fixed issue/owner/default branch, pinned checkout, environment-scoped secrets and encrypted-only result posting; its actual workflow in .github/workflows stays blocked. Only the later reviewed main commit can run issue_comment. Explicit separate approval is required for promotion and enabling the environment/variable. Runner env secret placeholders: PRP_REX_V11_HOST (exact dedicated host DNS), PRP_REX_V11_SSH_KEY (new restricted identity, no V1 key), PRP_REX_V11_KNOWN_HOSTS (out-of-band verified host key, never trust ssh-keyscan alone). PRP_REX_V11_ENABLED absent/false by default. No artifact access initially: no producers/redirects/actions permission; repository and inline sources only. Runner token scoped contents:read/issues:write; server reads public Owner API without token. No secret output. Separate per-request reply certificate/private key; only recipient public cert and pinned server signing cert are distributed. On host fixed config root:receiver-group issue=506 and recipient.crt, signer.crt 0444; recipient.key, signer.key 0440 with separate keypairs. Public files require receiver group as well. Never share signing/decrypt private keys; do not place secrets or raw output in the public repo. Chat approval is not independently attested by GitHub owner identity.

## Forced command (template; no installation)
Receiver currently nologin. Later explicitly authorize a root-owned, immutable dedicated login wrapper, NOT unrestricted bash/sh login. sshd invokes the configured login shell with -c; wrapper accepts only two arguments, -c and the fixed literal prp-receive-v11, checks SSH_ORIGINAL_COMMAND is receive-v11, then execs system Python with -E -s and fixed bridge.py receive-v11. Other inputs fail with no shell evaluation. Worker stays nologin. Exact wrapper candidate:
~~~sh
#!/bin/sh
set -eu
[ "$#" -eq 2 ] && [ "$1" = -c ] && [ "$2" = prp-receive-v11 ] || exit 2
[ "${SSH_ORIGINAL_COMMAND-}" = receive-v11 ] || exit 2
exec /usr/bin/python3 -E -s /opt/matrix-prp-remote-executor-v11/src/bridge.py receive-v11
~~~
Review-only sshd Match block, scoped to receiver; preserve other users and global policy. Use root-owned authorized_keys path and independently verified dedicated public key; restrict/command option on key too. Verify sshd -t and sshd -T -C for receiver and existing users before separately approved reload. Verify locked password/publickey/PAM/shell compatibility on disposable target first; do not disable existing host security controls. No key generation or real configuration yet.
~~~text
Match User prp-remote-v11
    AuthenticationMethods publickey
    PubkeyAuthentication yes
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AuthorizedKeysFile /etc/matrix-prp-remote-executor-v11/authorized_keys
    ForceCommand prp-receive-v11
    PermitTTY no
    DisableForwarding yes
    PermitUserRC no
    MaxSessions 1
Match all
~~~
Also verify effective PermitUserEnvironment=no and no agent, X11, port or Unix socket forwarding; root-owned wrapper rejects interactive/nonmatching commands. Authorized key line template: restrict,command="prp-receive-v11" <NEW_DEDICATED_PUBLIC_KEY>. No SSH daemon start or change in this phase.

## One-shot service initialization (review only)
Keep existing worker.service.review unchanged on host. A future separately reviewed unit must use exact name prp-remote-executor-v11.service, Type=exec, User/Group=prp-remote-worker-v11, ExecStart=/usr/bin/python3 -E -s /opt/matrix-prp-remote-executor-v11/src/executor.py worker-once, working directory fixed. NoNewPrivileges=yes, CapabilityBoundingSet= empty, MemoryMax=512M, MemorySwapMax=0, TasksMax=64, CPUQuota=100%, KillMode=control-group, RuntimeMaxSec=260 (15s listen + 240s handoff + margin), TimeoutStopSec=5. Require sandbox and worker gates. Root-managed /run/prp-remote-v11-handoff owner worker:GID receiver, mode 2750, recreate on reboot via separately authorized tmpfiles entry. The handoff service (distinct from worker) uses User/Group=prp-remote-v11, Type=oneshot, ExecStart fixed bridge.py handoff-once, Requires/After=prp-remote-executor-v11.service, TimeoutStartSec=260, MemoryMax=256M, MemorySwapMax=0, TasksMax=32, CPUQuota=100%, empty capability set, NoNewPrivileges, KillMode=control-group. Require receiver/worker/sandbox gates. Only start coordinated handoff after a verified submit; no timer in first smoke. Test startup ordering/peer credentials, actual systemd resource bounds and cgroup cleanup on disposable host; if production shared host cannot meet controls, stop. Rootfs and spool app-level bounds are not kernel quota; no production mounts, Docker, sudo or arbitrary host commands. Existing 1024 durable request cap fails closed, no replay ledger deletion. No automatic execution or publication retry.

## Activation boundaries
Before first real smoke: review adapter/template plus independent Security Review or explicit residual-risk decision, target rootfs provenance and isolation checks, verify all gates absent, exact installed three source hashes, no production restart, pinned known_hosts, separate real credentials and restricted login, root-owned configuration, short-lived explicit staging-only approval and separate default-branch trusted workflow promotion. Post a harmless inline script only after approved activation; separately approved result query with fresh nonce; verify encrypted receipt and no raw output, one-time execution, close all gates after test. Never reuse production V1 or enable deploy. Any later artifact support requires exact producer/redirect allowlist and separate validation.
