# PRP production health MCP preparation

Status: code and isolated-test candidate only; NOT a production rollout approval.
The owner selected the plugin name **PRP** and this first release surface:

- Structured meals (including clearly identified event calorie estimates), exercise,
  and weight/body-fat/waist records: create/read/update/delete.
- Public/owned food search and daily health summary: read only.
- Personal dish templates, goals, profile editing and other modules are deferred.

## Permission contract

Only these six scopes are proposed for the production issuer, resource metadata,
ChatGPT grant and PRP owner consent:

```
prp.wellness.read
prp.wellness.write.create
prp.wellness.write.update
prp.wellness.write.delete
prp.wellness.write.status
prp.wellness.write.confirm
```

The fixed manifest exposes nine health tools. It cannot expose tasks, finance,
generic record writes or generic draft confirmation through these scopes.
Never add `prp.write.*`, `offline_access`, task or finance scopes to make linking work.
First-party identity binding accepts owner-approved health read consent without
requiring task access. The grant UI obtains selectable permissions from the current
origin's resource metadata and selects only a read scope by default; failed discovery
leaves no selectable grant. Server consent validation remains authoritative.

MCP proposals still require a separate first-party PRP password approval. Confirm
rechecks the operation scope and the current owner grant. Parent and food rows are
locked and compared against approved snapshots. The existing one-use MCP draft
transaction writes the health row and consumes the draft atomically. Replays return
the result; expiry/rejection/conflict cannot force a write. No migration is added;
the three new kind strings fit the existing V25 `VARCHAR(16)`.

Catalog items use exact accessible food IDs and weights; their calories/macros
come from the catalog. Estimated event items have no food ID and need an explicit
name and calories; macros stay unknown. The MCP tool does not call an AI model or
USDA service, and a personal record is never passed off as a structured meal.

## Proposed configuration values, not an executable installation

- Resource: `https://micor.top/api/mcp`
- PRM: `https://micor.top/.well-known/oauth-protected-resource/api/mcp`
- Issuer: `https://auth.micor.top/realms/prp-mcp-prod`
- JWKS: issuer + `/protocol/openid-connect/certs`
- First-party callback: `https://micor.top/prp/me/mcp-link/callback`
- Client metadata ID: `https://chatgpt.com/oauth/client.json`
- Authentication: `private_key_jwt` and PKCE S256. No anonymous DCR.

The candidate adds opt-in `MATRIX_PRP_MCP_PRODUCTION_WELLNESS_ONLY=true` with
MCP/OAuth/write enabled, Flyway disabled and the six exact health scopes above.
`production-tasks-only` must be false: its read-only invariant must not be weakened.
The expanded-account allowlist must use the owner's independently verified
**production** ID; do not copy staging ID 2, a password or a consent row.
No owner ID, credential or live key is included in this repository.

The frontend must be rebuilt with the independently reviewed production first-party
authorization endpoint. Do not reuse a frontend pinned to the test issuer.
The separate production Keycloak build must enforce the production resource and
realm in every policy, token exchange, refresh/revocation and audience mapper.
The staging CIMD extension is not approved for reuse merely because its test flow
works. Pin the actual source/JAR/image and verify official compatibility first.

## Outstanding production gates

1. Reconfirm current main, production SHA/V29, complete Nginx and service baselines.
2. Review DNS/CAA, create the approved `auth.micor.top` record and issue its certificate
   using an actual ACME challenge. Existing micor.top SANs do not cover this hostname.
3. Provision independently reviewed production auth containers/network/limits,
   PostgreSQL volume, Realm, signing keys and constrained metadata/JWKS egress.
4. Back up the current V29 production database; prove recovery on an isolated clone.
   Back up/restore the new auth state and signing keys separately. Do not back up videos.
5. Run the full isolated OAuth/browser/health CRUD/isolation/revocation tests on the
   exact production candidates; synthetic signing keys are not real ChatGPT proof.
6. Review exact configuration diffs, SHA256, memory budget and rollback commands.
   Root-owned production configuration installation, PRP restart, auth startup and
   Nginx reload require explicit approval of that concrete change package.
7. Add exact MCP/PRM Nginx routes only; preserve Matrix `/api/`, PRP `/prp/api/`,
   Host/SNI guards, TLS, rate limits and all existing sites. Auth admin/master/DCR
   remain inaccessible. Verify the complete configuration in isolation first.
8. Have the owner log into the production PRP account, consent to health scopes,
   bind production identity, then personally create/connect **PRP** in ChatGPT.
   Validate real signed exchange, health tool discovery, human approval, persistence,
   cross-user refusal and immediate revocation. Do not declare this completed in CI.

Rollback restores only that rollout's configuration and application settings,
withdraws new MCP/auth routes and stops only new auth instances, retaining their
volumes and keys. Do not restore pre-V29 SQL over V29 or modify Flyway history.
If rollback fails, report `RECOVERY_REQUIRED`.
