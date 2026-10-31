# Review only: preserving MCP V2 while reconstructing the Nginx guard pair

**Status:** 2026-10-26 `NO-GO`. This is a review artifact and **cannot**
authorize an Nginx install, B2 cutover, Keycloak change or `main` merge.

## Actual operator results (reported, not independently SSH verified)

The original B2 verifier `verify_guard_release_gate.py --evidence-only`
returned `ISOLATED_GUARD_EVIDENCE_PASSED` (0), but its full read-only
prechange gate returned `PRODUCTION_NGINX_GUARD_NOT_INSTALLED_OR_DRIFTED`
(2). Metadata inventory reported **both** `approved-install.safe.json` and
`fresh-b2-restore.safe.json` absent. Subsequent read-only active-state
inventory matched ordered Nginx config path sequence.

Actual test vhost `/etc/nginx/conf.d/prp-mcp-test.conf` has SHA256
`35bb31322b23efef536c97e12619ceac7087aa4cf2d56c57f3307232f9362397`;
it contains exactly **two** `127.0.0.1:18082` references and zero
`18081`. It matches the byte-pinned 2026-10-22 backup SHA256
`be7d4ba493f38280918cc7ec775f7759c150fea23d466f74358c06188403fa0d`
**after only substituting two `18082` ports back to `18081`**.
No other byte differences. Production default `micor.top.conf` matches
its original known rollback SHA256
`ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b`.

Historical guard-only test vhost SHA256
`90814118bda4c8ca0be3d87ae36accb003a4be7f593954d552bfe05c1c98e6bd`
points **twice** to **18081**. Blindly installing it would route MCP away
from the live V2 test gateway at loopback **18082**, potentially breaking
V2 integration. The original B2 candidate points at 18081 too and is
NOT the guard-only candidate to install.

The *hypothetical* V2 guard-only test vhost with the two exact old-to-new
port substitutions has projected SHA256
`728b4a3290353f90ea692a2e1ae38a1656101e4381ee3bbdbce6c1cb80964421`.
The companion default guard file is unchanged from the historical candidate,
SHA256 `da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b`.
These two review hashes **do not** mean the resulting pair is safe to
install or already tested against public traffic.

## Code-only review preparation

`prepare_v2_guard_review.py` validates exact SHA256 for both live vhosts,
both verified 2026-10-22 rollback files and both original guard-only
candidates. It also asserts that the live test vhost differs from the
historical backup **only** at the two expected proxy ports, and verifies
the projected V2 guard SHA256. It does not require downloading live
configuration into CI.

Default invocation is **read-only**:

```sh
python3 prepare_v2_guard_review.py
```

For an independently reviewed, optional disk artifact, it can place
**two private REVIEW files only** in a brand-new, explicitly named
`/root/prp-mcp-cimd-stage-b/review-only-v2-guard-<suffix>` directory.
Only the reviewed vhost pair and `review-report.json` will be created.
It will never overwrite files, modify `/etc/nginx`, change originals,
create `*.safe.json` receipts or call a reload. The resulting review
directory is **not** an installable release package or signed manifest.

## Independent work required before any installation approval

1. Keep the original 2026-10-22 guard, backups, manifest, evidence and
   original verifier **unchanged**. A new V2 candidate needs its own
   versioned manifest and auditable provenance; never rewrite old
   evidence hashes to make `verify_before_b2` pass.
2. Validate the **entire paired rendered Nginx configuration** with
   appropriate staging certificate material and the original Host,
   Authority, HTTP/2, IPv6, route, upstream, 421/no-upstream and
   expected-acceptance regression suites. A successful hash-only or
   syntax-only check cannot replace that.
3. Reconcile the exact V2 MCP `18082` resource, issuer, metadata,
   public endpoint, and expected back-end identity/linking allowlist.
   Review whether later legitimate V2 changes require an expanded,
   independently approved route surface; never permit all `/api/**`.
4. Diagnose historical public IPv6 normal-path timeouts and prove
   independent real-network acceptance. A timeout or a failed request
   is not automatically a safe 421 rejection. Define rollback, backup
   and live service impact boundaries, especially with only one 4C8G
   production host and the shared vhost map.
5. Only after **separate explicit user authorization for the exact
   guard-only installation** may an approved operator conduct atomic
   paired installation, `nginx -t`, controlled reload, external
   acceptance and guarded rollback. Only actual successful installation
   can justify authentic `approved-install.safe.json`.
6. A **separate explicit B2 authorization** plus fresh <=3600-second
   independently recovered PostgreSQL backup with all table fingerprints,
   signing keys and signed dump SHA can justify the new
   `fresh-b2-restore.safe.json` and guarded cutover. No synthetic receipts,
   force-false-to-true edits or silent gate bypass.
7. After all gates, real ChatGPT OAuth, owner pairing and
   `prp_tasks_list` read acceptance remain separately unproven;
   keep write tools OFF and both PR #95/#113 Draft.

The generated V2 review pair does NOT meet any of the above independent
release or human-approval requirements by itself.
