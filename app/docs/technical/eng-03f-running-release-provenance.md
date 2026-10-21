# ENG-03F — Independently assess the running JAR / release mismatch

**Status: Draft, review-only, no host access or installation.**

ENG-03E proved that two *CI-built* executable JARs serve private finance
HTTP APIs on synthetic expanded databases; it did **not** prove that either
JAR is the byte-identical executable actually running in production.

ENG-03F adds two **separate, non-authorizing** capabilities:

- `app/deploy/collect_running_release_evidence.py`: a proposed
  **administrator-executed**, no-argument, read-only local collector.
  It validates a fixed `/srv/matrix-prp/releases/current` pointer, strict
  `release.json` and `backend.jar` SHA256, the active systemd MainPID, and
  the resolved `-jar` target in that specific process's `/proc/PID/cmdline`.
  It also computes the existing controller's SHA256. It emits only whitelisted
  metadata. Errors have no verbose output. The command is **not**
  automatically installed or added to the deployment/inspection SSH gateway.
- `app/deploy/reconcile_running_release.py`: an **offline reviewer**
  checks supplied collector JSON against byte-for-byte `release.json`
  metadata from the trusted release artifact and the independently reviewed
  `controller-manifest.json`. Stale/future reports, duplicate JSON fields,
  mismatched release identity, old schema version, JAR file digest, metadata
  digest, controller digest or unexpected private fields are rejected.

Example offline validation **after an authorized administrator has independently
collected a safe report**, on a trusted local review machine:

```sh
python3 app/deploy/reconcile_running_release.py \
  --observation /review/observed-running-release.json \
  --release /review/reviewed-artifact-release.json \
  --manifest app/deploy/controller-manifest.json
```

The collector itself, after **separate administrator code/permission review**,
may be run locally with no arguments as root, without any SSH gateway changes:

```sh
sudo /usr/bin/python3 -I app/deploy/collect_running_release_evidence.py
```

Do **not** run the unreviewed PR source directly on production. Its expected
service `-jar` command form, path layout, metadata owner/mode, process
argument format and installed controller digest must first be checked against
the real host. No raw `systemctl` output, process command line, JDBC
connection strings, SQL, JWT, API keys, user IDs or private media are emitted
by the helper. Neither tool contacts production over a network.

## Evidence interpretation

Passing comparison returns **`MATCHES_SUPPLIED_METADATA_REVIEW_REQUIRED`**,
**not** `PRODUCTION_ATTESTED`, `DEPLOY_READY` or a publication pass token.
It always includes:

- `live_host_independently_attested: false`
- `real_production_jar_verification_completed: false`
- `production_authorized: false`

The collector's JSON has the same status restrictions. A JSON document can
be fabricated by an attacker with write access; a SHA digest only binds bytes,
not the identity of the person/host that measured them. Comparing **provided**
JSON alone cannot establish independent authenticity. The administrator
must verify trusted execution, freshness and chain of custody in a
**separate** reviewed process. An observed process `-jar` file path does
not attest which bytes the JVM originally loaded if the file was replaced
in place; it only verifies the current file and pointer. An authentic
production attestation therefore needs additional immutable artifact, host
and process-lifetime evidence.

No new outbound production credential, remotely callable privileged helper
or restricted-identity SSH case is created. No changes to GitHub production
environment rules, controller allowlist, Flyway migration policy or database
occur in this stage.

## What is still blocking ENG-03 production expansion

1. **Independent live provenance:** a reviewed/approved host measurement of
   the running JAR, release commit, process lifetime and the trusted
   immutable artifact; verify that production is actually at the claimed
   release, not merely the current GitHub `main`.
2. **Actual preceding release binary:** retrieve only through a separately
   authorized, provenance-verified channel and run genuine **old** and
   **candidate** JARs against a *physically isolated* restored copy of
   a reviewed real production backup.
3. **Actual DB migration:** approved MySQL/version/table definitions, real
   backup restore receipt, column count/index/constraint/row fingerprints,
   metadata-lock review and DBA authorization.
4. **Controller governance:** independent root-controller patch approval,
   installed hash and SSH/forced-command inventory, approval hold and
   explicit release decision. No generic `ALTER` permission is added.
5. **Post-cutover:** health, authenticated private APIs, Flyway state,
   independently measured runtime JAR and historical-data preservation
   before declaring any deploy successful.

Until then, **ENG-03A–F remains non-authorizing Draft work**. Existing
`create-empty` restrictions continue to reject `ALTER TABLE` on old
PRP tables. Do not merge these changes merely because CI passes on synthetic
fixtures; a merge to `main` can trigger production auto-publish.
