# ENG-03E — executable JAR HTTP compatibility proof (CI only)

**No production deploy, schema migration or controller upgrade is authorized.**

This stage extends ENG-03D (PR #99) by packaging two independent runnable
Spring Boot **JAR files**, launching them as separate **Java processes** and
making real HTTP requests over `127.0.0.1` against two separately expanded
MySQL 8.4 databases in a disposable CI runner.

## Exact test path

1. Check out `main` as a separate baseline alongside the candidate PR SHA.
   Reject a candidate source SHA mismatch.
2. Run ENG-03D's full existing integration suite and schema setup first,
   including the additive nullable `schema_probe` column in both DBs.
3. Package each checkout with `./mvnw -B -DskipTests package`, capturing the
   exact source SHA and executable `backend.jar` SHA256 for that checkout.
4. Start each process on a *fixed localhost-only* port (4181 baseline, 4182
   candidate), without the in-memory `test` Spring profile. Reuse only
   synthetic CI bootstrap users, JDBC credentials and private data roots.
5. Probe `/api/health` readiness, unauthenticated finance denial, authenticated
   `/api/auth/login` and `/api/users/me`, a private expense write/read, and
   second-user invite/registration that must not expose the first user's row.
6. Stop each process and verify the second process independently. Upload
   a JSON receipt containing only source SHA, JAR SHA256 and PASS checks;
   **never** include JWTs, account credentials, user data or application logs.

The CI job is named `expanded-schema-backend-compatibility`, with an
additional packaged-JAR step and `prp-ci-synthetic-jar-http-provenance`
artifact retained for 14 days. Those checks are blocking. A failed HTTP test
is **not** silently replaced by a MockMvc test.

## Trust and scope

The evidence is explicitly classified `CI_SYNTHETIC_JAR_HTTP_PROBE`, with
`production_deployment_attested: false` and
`production_authorized: false`. SHA256 is a content fingerprint, *not*
a source signature, independent provenance, or verification that a file
matches the server's current release.

The `main` checkout is the branch HEAD **at CI checkout time**. It is not
proven to equal the deployed production release. The candidate JAR is built
from PR source in CI; it is not the independently reviewed production release
artifact. The tests demonstrate two runnable JARs behave correctly on
synthetic, expanded schemas; they do not validate actual old deployed
JAR/Web, production configuration, media data, storage layout, or genuine
backup recovery. Ports and DB names are fixed; CI must never take a URL,
SSH key, release-controller privilege or production DB connection as input.

## Remaining approval blockers

- Independently attest production `release.json`, running commit and exact
  **installed JAR** SHA256; match them to a trusted artifact without exporting
  private user data.
- Independently obtain the **actual former executable JAR** and proposed
  candidate, validate artifact signatures, test with a restored production
  backup in a physically isolated environment and verify tenant/ownership,
  history, data fingerprints, shared API/Web compatibility, and application
  rollback.
- Get DBA authorization for real SQL and lock-sensitive migration behavior,
  approved root controller patch, installation/SSH policy attestation and
  protected-main production acceptance.
- Keep ENG-03A/B/C/D/ E in Draft pending independent review. Preserve the
  existing `create-empty` production migration policy. No V24 or automated
  production `ALTER TABLE` is introduced by any of these tests.
