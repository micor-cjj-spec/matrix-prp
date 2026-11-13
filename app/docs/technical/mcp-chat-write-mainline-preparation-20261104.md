# ChatGPT chat-write integration preparation

This branch prepares reviewed code and CI for main. It does not merge main,
deploy any service, change an active Realm or migrate a live database.
The checked-in publication hold and default-disabled MCP/OAuth/write settings
remain mandatory. Removing that hold requires a separate application-release
review, including updating the explicit integration hold assertion.

## Source and operational changes

The integration starts from main `528c54c` and incorporates the running staging
source `8728277`. That source already includes the MCP gateway, V28/V29 lineage
reconciliation, first-party identity binding and incremental OAuth challenges.
No historical SQL is changed. Separate overlapping discovery proposals still
require deliberate reconciliation; this is not approval to merge every old PR.

Public staging has two OAuth reverse-proxy hops. Both need the bounded settings
returned by `oauth_proxy_buffers.render_oauth_header_buffers()`:

```nginx
proxy_buffer_size 16k;
proxy_buffers 4 16k;
proxy_busy_buffers_size 32k;
```

`proxy_buffering off` alone does not remove the response-header buffer limit.
The CI fixture proves a synthetic 6.5KB response header succeeds only when both
hops are configured, and a 20KB header still fails. It verifies the CI CA and SNI
on the client and between proxies; it does not disable TLS verification.

`render_tls.py` retains its older review-only topology and is **not** the complete
installed strict public vhost. Do not replace a live Host/SNI allowlist with that
older broad renderer. `render_internal_oauth_tls.py` records the isolated internal
two-SNI topology. Its legacy PRP SNI is not the V2 database route.

For the existing strict public staging vhost, review the buffer snippet only
inside the OAuth server block, preserving all existing guards, certificates and
location allowlists. Internal single-file Docker bind mounts require an explicit
inode-aware installation plan; an atomic host rename alone may leave a container
reading the old mount. None of these generators installs or reloads anything.

The first-party browser surface must match its backend:

- The old `render_readonly_link_routes()` remains read-only and excludes approval.
- Explicit `render_v2_write_routes()` includes the approval page plus UUID-only
  GET review and POST approve/reject routes along with the existing V2 bootstrap
  routes. All use the same `127.0.0.1:18082` V2 gateway, never the older 18081
  database or the PRP SNI behind 18443.
- Review in the existing Host/SNI/Origin guarded server. Do not append duplicate
  locations or open `/api/mcp/approval/**` as a generic prefix.
- JWT ownership, password step-up, expiry, consent, write flag and exactly-once
  consumption remain application checks. Proxy reachability is not approval.
- Generated routes are no-store, raw-URI/method checked, body bounded and do not
  record approval URLs or passwords in access logs. Keep the parent error log
  privacy policy as well; do not publish raw server errors.

Before an independently approved rollout: compare exact active bytes and the
reviewed diff, create a new private backup, `nginx -t`, one graceful reload,
server and external acceptance. Failure restores that transaction's original
bytes and permits one rollback reload; never automatically reinstall or weaken
an assertion. Mainline code preparation is not that rollout authorization.

## Unified CI

The existing `CI` workflow invokes the reusable disposable suites in
`app/deploy/mainline-mcp-ci-contract.json` from the same repository commit.
They run for main PRs without depending on the old feature-branch paths filters.
They have contents-read permission, no inherited Secrets and no production
environment. Existing backend, Web/mobile, MySQL and migration jobs remain.

The additional real Nginx fixture covers bounded two-hop headers, approval API
reachability with unauthenticated 401, method/UUID/raw-path denial with zero
synthetic-upstream calls, wrong Host and Origin. It contacts only loopback and
uses temporary synthetic certificates and no live data.

All final-SHA jobs must pass. A prior branch's green run or a skipped publish is
not a substitute. Tests using exact ChatGPT client IDs and temporary CI signing
keys do not verify OpenAI's actual private-key assertions.

## Real ChatGPT positive evidence, reviewed 2026-11-04

The owner identified the existing ChatGPT conversation titled
“创建工作任务草稿”. It records preparation of a personal record draft, the owner's
browser approval, and ChatGPT's successful confirmation reply.

A separate administrator **SELECT-only** check corroborated that the identified
draft is `CONSUMED`, has both approval and consumption timestamps, and its saved
record exists under the same staging owner. Neither the record body nor password,
JWT, authorization URL or health details was read or exported. Private row and
conversation identifiers remain outside this repository.

This establishes the real-client positive path:

`ChatGPT prepare -> owner PRP password approval -> ChatGPT confirm -> owned row`

The thread API exposed conversation summaries, not the raw MCP tool response.
The database corroboration proves persistence but is not a captured cryptographic
client-assertion trace. Real ChatGPT replay, cross-user attempts and revocation
have not been re-executed by this preparation task. Disposable CI checks those
negative contracts separately; do not label them real-client evidence.

The saved object is a **personal record**, not a structured wellness meal.
Dietary/calorie statistics require a separate typed MCP tool and corresponding
owner-approval/validation/idempotency tests. Do not convert an existing RECORD
draft into a different business operation or claim full CRUD for every module.
