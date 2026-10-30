# B2 isolated app-restore cleanup — operator-reported evidence (2026-10-30)

**Cleanup: PASS. B2 authorization: NO-GO.**

Following successful isolated PostgreSQL restore, Keycloak 26.8.0 startup and `prp-mcp` OIDC discovery HTTP 200, the operator executed a guarded cleanup script.

Before removal, the script checked:
- Original archive SHA256: `0ffedd753d535c80d833e0239789a37ab5a9316f989cfc5697263e38a6951c17`.
- Docker network `prp-mcp-b2-apprestore-net` was internal.
- Both named containers belonged to that network.
- The isolated network contained exactly two containers.

Operator terminal output:

```text
=== 5. 删除临时容器 ===
prp-mcp-b2-apprestore-kc
prp-mcp-b2-apprestore-db
=== 6. 删除临时网络 ===
prp-mcp-b2-apprestore-net
CLEANUP=PASS
ORIGINAL_BACKUP_PRESERVED=YES
B2_DEPLOYMENT_PERMITTED=NO
```

This records a successful cleanup command sequence, not an independent host inspection. The ephemeral restored database copy was destroyed; original archive preserved.

**Unresolved:** independent B2 acceptance, explicit change authorization, and live ChatGPT OAuth verification. No approval receipt is issued or implied by this record.
