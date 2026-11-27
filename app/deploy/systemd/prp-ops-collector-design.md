# D-M04 独立采集运行与读写隔离（离线设计）

## Scope / safety
This is an offline implementation and unit-file review only. Neither systemd unit is installed, enabled, started, nor validated on a live host. Live collection remains OFF unless a root-owned marker with exact bytes `host-metrics=approved\n` exists at `/etc/matrix-prp-ops/ALLOW_HOST_METRICS`; both units also have `ConditionPathExists`. The marker is absent from the repository. M06 remains separately gated. No host connection, network, SSH, shell, DB, Docker socket, process enumeration, deployment, or production change.

## Collector
- Fixed allowlist only: `/proc/stat`, `/proc/meminfo`, and `statvfs("/")`; no user-controlled path, environment target, command or argument.
- CPU samples are separated by one second; timer cadence 30 seconds. No network health probe yet: the repository's Spring application listens on port 8080 in its own runtime configuration, while the deployment-specific host loopback upstream has not been verified. Application/readiness remains `unknown`; do not assume port 11000 or send a probe.
- Procfs reads are bounded to 64 KiB. Individual source errors become null metrics; collection does not leak source details.
- A fixed root-owned marker is checked again by Python even though systemd has a matching condition. Marker must be regular, root:root, 0644, single-link, exact size and exact content.
- A fixed `flock(LOCK_EX|LOCK_NB)` file in systemd's private `RuntimeDirectory` prevents overlapping collector instances. Timer is monotonic OnBootSec/OnUnitActiveSec 30s; it is not enabled by this change.

## Process and file ownership
- Writer account: `prp-ops-collector`; shared group: `prp-ops-snapshot`; future MCP reader account: `prp-ops-mcp` with shared group as supplementary read-only group.
- Pre-provisioned `/var/lib/prp-ops`: writer:shared-group, exact mode `2750` (setgid). Snapshot: writer:shared-group, exact mode `0640`. The writer verifies ownership before atomic replacement; the reader verifies it before opening and exposes only `read_raw/read`, no write method. Reader UID must differ from writer UID and must belong to the shared group. The group has read/execute only on directory and read only on file.
- Root/admin provisioning of accounts, directory, source copy, marker, timer activation and any live installation is intentionally not automated or executed. The MCP reader service itself is not yet implemented; no unit is provided for a nonexistent server.

## systemd template
`prp-ops-collector.service` is oneshot, non-root, no capabilities, no network address family except AF_UNIX, strict filesystem sandbox, private tmp/devices, no-new-privileges, fixed writable snapshot and runtime directories, resource ceilings and eight-second timeout. Timer is a separate template and has no activation by default. Both require the root-owned marker. CI parses and checks the templates; it does not install, start, or invoke systemd.

## Remaining risks / gates
- Separate UID/GID semantics and file permissions are tested with synthetic local users/temporary directories, not actual system accounts or a live host.
- Root marker provisioning and systemd support for sandbox directives require target-host compatibility validation before any install.
- Clock synchronization, reboot behavior, timer missed-run behavior and collector runtime budget require non-production acceptance.
- MCP reader's OAuth/JWKS verification, authoritative grant/revocation adapter, network service, rate limiting, audit and response-delivery revocation race remain unimplemented.
- Do not expose host-wide metrics when staging and production share the same host until the owner approves the exact disclosure boundary.
- No database, application, Keycloak, shared OAuth, GitHub release lock, V1 Shell, main/dev merge or production deployment changes.

### Explicit host-metric disclosure gate
The marker name `ALLOW_HOST_METRICS` is intentional: CPU, RAM and root-filesystem figures are host-wide and may reveal shared production/staging capacity. A future administrator must explicitly provision the root-owned marker with exact content `host-metrics=approved\n` only after confirming the host/environment disclosure boundary. The marker is absent and must remain absent until separate M06 authorization. No per-container substitution is implied.
