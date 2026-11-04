# Current test Keycloak restore — technical acceptance record, 2026-10-28

> **TECHNICAL REHEARSAL PASS, CHANGE AUTHORIZATION STILL NO-GO.**
> This file records operator-provided, successful, SHA-pinned terminal
> evidence. It is **not** an independently signed G0/B2 acceptance,
> installation approval, backup receipt, or permission to mutate active
> Keycloak/PRP/Nginx.

## Actual operator-invoked source and backup

- Source commit (immutable): `cf8471cc70493d45b81115add5f32970fff6871e`.
- Entry point: `app/deploy/mcp-oauth/keycloak-resource-guard/verify_restored_realm_spi_clone.sh --current-snapshot`.
- Mode: `CLONE_SNAPSHOT_KIND=CURRENT_PINNED_AT_2026_10_28`.
- Snapshot: `/root/prp-mcp-backups/keycloak-current-review-ET1EMnba/keycloak-current.dump`.
- Actual backup digest: `52b67c64a8e37679cd5b3999057cd035b2c198ce6e57cf4a7dcbcc494a45e8bd`.
- Backup size: `268204` bytes; first captured via pinned `capture_current_keycloak_review.sh`, checked as `PGDMP` / parseable by `pg_restore --list`.
- Both outer `git fetch` and exact `FETCH_HEAD == PIN` passed.
- The command output ended `CURRENT RESTORE REHEARSAL COMPLETE`.
- Backup data and signing material remain private on the host; **never** upload the dump, credentials, OAuth codes/tokens, private JWKs or Docker environment to GitHub/ChatGPT.

## Successful actual isolated restoration and tests

| Operator-reported check | Reported result | Meaning |
| --- | --- | --- |
| Existing JDK21 used / Maven compilation | `HOST_JDK21_COMPILER=PASS` / `HOST_JDK21_MAVEN` | Builds clone-only SPI provider; no host Java install |
| SPI security JUnit tests + archive structure | `PASS` / `PASS` | Candidate validates as built on this host |
| Candidate JAR SHA256 | `0b505854dfd03f9c3ce7e8ab42603a7ecf01c3cead93804a3723946a7d0a65bb` | Build output recorded; does not authorize install |
| `pg_restore` into isolated PostgreSQL | `RESTORED_TABLES=101` | Actual current dump restore (not archive-list only) |
| Private Keycloak starts | `CLONE_KEYCLOAK_READY=YES`; `RESTORED_OIDC_HTTP=200` | Recovered clone serves OIDC |
| Restored public signing JWKS matches active Realm | `RESTORED_SIGNING_PUBLIC_JWKS_MATCH_LIVE=YES` | Public signing-key parity at verification time |
| Original clients before change | `CLONE_EXISTING_CLIENTS=13` | Expected exact count in restored current snapshot |
| Existing audience mapper candidate repair + rollback | `CLONE_AUDIENCE_MAPPER_REPAIR=PASS`; `CLONE_AUDIENCE_MAPPER_ROLLBACK=PASS` | No lingering mapper diff |
| Exact ChatGPT and PRP first-party client create | `RESTORED_13_CLIENT_EXACT_TWO_CREATES=PASS_PRIVATE_CLONE_ONLY` | Both reviewed clients created only in clone |
| Exact two-client rollback | `RESTORED_13_CLIENT_EXACT_TWO_ROLLBACK=PASS_PRIVATE_CLONE_ONLY` | Both removed, original clients/policies/scopes reverified |
| Existing clients after clone-specific SPI exercise | `CLONE_ORIGINAL_13_CLIENTS_UNMODIFIED=YES`; `CLONE_RESTORED_13_CLIENT_INVENTORY_PRESERVED=YES` | Original 13-client identity/configuration preserved |
| Refresh/resource scope + negative security cases | `CLONE_RESTORED_SPI_REFRESH_GRANT=PASS_SYNTHETIC_PASSWORD_GRANT`; other controls `PASS` | Synthetic test user/flow, **not** real ChatGPT |
| Synthetic user/realm settings/policies restored | `CLONE_RESTORED_SYNTHETIC_USER_REMOVED=YES`; `CLONE_RESTORED_REFRESH_REALM_SETTINGS_ROLLBACK=PASS`; `CLONE_RESTORED_POLICY_ROLLBACK=PASS` | Clone cleanup and policy preservation checks |
| Active test Realm changed | `ACTIVE_REALM_CHANGED=NO` | No live Realm client registration |
| Isolated Docker network/container/volume cleanup | `CLONE_CLEANUP_RESOURCE_STATUS=0` | No named disposable clone leftovers reported |
| Overall clone script exit | `CLONE_SCRIPT_EXIT_STATUS=0` | Entire private rehearsal succeeded |

**Precise conclusion:** A current-date capture of the active **test**
Keycloak database was technically restored into a private clone with
the original 13 clients, and the clone's public signing JWKS matched
the active Realm at test time. Exact two-client additions and rollback
passed. This is stronger than the historical dump and CI synthetic
fixtures. It does not prove every encrypted secret, private signing
key operation, historical token/session, or every policy edge path
under actual ChatGPT assertions; only the listed technical checks
were performed. It is not an **independently attested** B2 restore
under the original controller's acceptance process.

## Remaining blockers — no additional identical restore loop

1. **Original B2/G0 authorization and provenance.** `B2_RECOVERY_GATE=NOT_COMPLETED`, `RESTORED_EXACT_CLIENT_B2_RECEIPT=NOT_ISSUED` and last reported `approved_install=MISSING`, `fresh_b2_restore=MISSING`. The original authorized independent reviewer/controller must decide whether this exact current-snapshot technical evidence satisfies their restoration standard, and independently issue/authenticate whatever receipts the *actual* gate requires. The assistant must not create, copy or manufacture them.
2. **Exact live Realm change review.** Verify current active policy/profile/executor and the existing 13-client/scope/mappers inventory, including the Keycloak CIMD parser interaction. Have the authorized operator approve the bounded **create-only two-client** diff and a rollback owner/abort rule; never silently disable a functioning unrelated policy.
3. **V2 runtime/front door parity.** Source images and disposable browser/Keycloak/Nginx tests are not deployed V2 `127.0.0.1:18082`. Existing old backend/Vue and six-file Nginx lineage must be reconciled. Review precise `/prp/me/mcp-link/callback`, `/api/mcp/identity/oidc/start`, `finish`, static assets, raw URI, Host/SNI/TLS, and correct V2 data target. Do not expose broad `/api/**` or accidentally target legacy `18081` / NewDB `18083`.
4. **Real owner authorization.** Only after approved, separately monitored installation and runtime link, perform actual ChatGPT `private_key_jwt` + PKCE/OIDC, grant `prp.tasks.read` only, first-party PRP owner binding, wrong-user denial, revocation and at-most-20 `prp_tasks_list`. No production PRP Flyway or direct MySQL shortcut.

**Current decision: G0/B2 NO-GO; Draft PR #113 unmerged; active test
Keycloak, production PRP V24, older stage, V2 local Compose changes and
Nginx unchanged.** Do not rerun current snapshot restore absent evidence
drift, a newly captured snapshot, or an authorized independent review
requirement.
