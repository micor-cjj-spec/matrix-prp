# B2 PostgreSQL isolated restore: operator-reported evidence (2026-10-29)

**Status: TECHNICAL DATABASE RESTORE OBSERVED; INDEPENDENT B2 APPROVAL MISSING; NO-GO.**

This record transcribes the operator's terminal outputs in the support conversation. It is not a signed independent review, not a generated B2 receipt, and not proof that the Keycloak application can boot and authenticate against restored data.

## Original archive

- Path on host: `/root/prp-mcp-backups/snapshot-4G42atvf/keycloak-stage.dump`
- Format: PostgreSQL custom dump v1.16, gzip.
- Size: 268201 bytes; root:root, mode 0600.
- SHA256: `0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17`
- PostgreSQL and pg_restore: 17.6; dump source and pg_dump: 17.6.
- `pg_restore --list`: PASS; 532 TOC entries; realm, client and user_entity table and TABLE DATA entries present.

## Isolated restore performed by operator

- Reused local image `postgres:17.6-alpine`.
- Dedicated ephemeral container `prp-mcp-b2-restore-test`; `--network none`, no published ports, independent tmpfs, 512 MiB memory and 1 CPU limits; no existing DB volume mounted.
- `pg_restore --exit-on-error --no-owner --no-acl -U restore_test -d restore_test` completed with exit status zero.
- SQL counts in restored DB: `realm=2`, `client=20`, `user_entity=22` (whole restored database).
- Restored realm names: `master`, `prp-mcp`.
- Restored `prp-mcp` client count: **13**; exact `https://chatgpt.com/oauth/client.json` count: **0**.
- Live `prp-mcp` client count previously read as **13**, exact client count **0**. Matching counts do **not** prove full row-level or point-in-time equivalence.
- Container at verification: Running=true, OOMKilled=false.
- Cleanup: `docker rm -f prp-mcp-b2-restore-test`, operator output `CLEANUP=PASS`; original archive checksum unchanged.

## Evidence limits and remaining acceptance

1. Backup was restored to a PostgreSQL process and queried successfully. No restored Keycloak application boot/login/token issuance test has been performed.
2. Restore was executed by the operator; the assistant has not independently inspected the host or attested to a signed restore receipt.
3. Recovery time objective, recovery point objective, application dependencies and full row/data integrity were not independently verified.
4. Existing host-guard inventory reports `approved-install.safe.json` and `fresh-b2-restore.safe.json` missing; these must not be fabricated from this document.
5. Before any Realm write: independent review of fresh restore evidence, explicit approval scoped to the exact client and relevant policy, safe preflight and rollback plan.
6. OAuth CI with disposable keys is not proof of real ChatGPT OAuth exchange; live acceptance remains pending.
7. No Keycloak, Nginx, production database or PRP production deployment changes are authorized by this document.

## Reviewer decision (to be supplied by independent reviewer)

- Recovery test meets B2 requirements: **NOT YET DETERMINED**.
- Exact client registration change authorized: **NO APPROVAL RECORDED**.
- Deployment permitted: **FALSE**.
