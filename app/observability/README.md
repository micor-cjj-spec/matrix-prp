# P1 disposable monitoring experiment (#450)

Not a deployable stack. Never run on a PRP host or self-hosted runner. This experiment uses only an isolated GitHub-hosted runner, an internal Docker network, ephemeral volumes and no published host ports (the CI host probes addresses in the disposable internal bridge). No production environment, credentials, host filesystem mounts (except a generated synthetic Prometheus config), Docker socket in containers, privileged mode, existing OAuth, external metrics destination, or tunnel.

Candidate tags: Prometheus 3.13.5 LTS, Grafana 13.3.0, node_exporter 1.13.1. Source release references:
- https://github.com/prometheus/prometheus/releases/tag/v3.13.5
- https://github.com/grafana/grafana/releases/tag/v13.3.0
- https://github.com/prometheus/node_exporter/releases/tag/v1.13.1

The CI resolves each tag once and runs the resulting local image ID; evidence is not a pre-approved digest lock, SBOM or vulnerability audit. Test only; review trusted digest and security support before any deployment.

The first run stopped at docker port: an internal network did not yield the expected published port. The follow-up removes all published ports, asserts internal network and port-binding state, resolves private container addresses and adds limited exit/OOM diagnostics. See https://docs.docker.com/reference/cli/docker/network/create/ for host access to internal bridge addresses. The exact underlying first-run Docker stderr was suppressed, so the revised access path still needs CI validation.

## Evidence
- 30s scrape, 7d retention and 512MB TSDB retention-size target; not a hard disk quota because WAL/head and transient usage are additional.
- CPU, memory, root/container filesystem and network series; data originate on disposable CI runner/container, not actual PRP host, and cannot prove host collection semantics.
- Grafana authenticated datasource query and four-panel dashboard creation; unauthenticated dashboard search denied; no actual browser UI test.
- Simulated scrape target down/recovery and Prometheus/Grafana restart persistence using disposable volumes.
- Two Docker resource snapshots, active head series and short-run TSDB size. Docker stats memory is not RSS. Container limits: Prometheus 512MiB, Grafana 384MiB, node_exporter 128MiB, 0.75 CPU each. These are trial bounds, not measured sizing. A few minutes of data cannot establish peak loads, actual disk compaction or seven-day storage behavior.
- Use https://prometheus.io/docs/prometheus/latest/storage/ for preliminary estimates after actual series count; plan disk headroom beyond estimated blocks. Separate monitoring node remains preferred, subject to cost, network, measured capacity and user authorization.

P0 remains partial; P1 status pending until actual CI. No production installation, monitoring server purchase, public ports, Nginx/Keycloak/OAuth edits, real telemetry transfer, MCP expansion, V1 shell, branch merges or production lock changes. #309/#424/#443 remain untouched.