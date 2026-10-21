# ENG-03D · Spring Boot finance regression on expanded actual PRP schema

**Status:** CI-only, synthetic MySQL data. **Not authorized for production.**

The first three ENG-03 stages verified SQL syntax, review-only contract
fingerprints, logical-dump restore and metadata-lock timeouts using synthetic
fixtures. This stage goes beyond pure SQL: it runs the **actual PRP Spring
Boot finance application test context and authenticated MockMvc endpoints**
on a *real, fully migrated PRP MySQL schema* that has one synthetic nullable
column added to `prp_finance_transactions`.

## What CI runs

The new `expanded-schema-backend-compatibility` job:

1. Checks out two independent code revisions: the **current `main`
   repository baseline** and the **PR candidate**. Logs both exact SHAs.
   `main` is not assumed to be the JAR running in production.
2. Rejects differing V1–V23 SQL resources or historical bootstrapping SQL,
   rather than accidentally testing two different database designs.
3. Creates **two separate disposable databases** on the job's MySQL 8.4
   service. Both use all original V1–V7 bootstrap scripts plus V8–V23.
4. Adds the candidate-only test column
   `schema_probe VARCHAR(32) NULL, ALGORITHM=INSTANT` to the existing
   **real `prp_finance_transactions` table** in both test databases.
   This is *not* a Flyway V24 migration, release artifact, or change to
   production schema and requires no permission change.
5. Runs `FinanceLedgerDatabaseIT` and `FinanceImportDatabaseIT` from
   **each** checkout against its **own expanded DB**, including login,
   account balance and transaction APIs, idempotent transfers/imports and
   ownership separation. Spring Boot, real MyBatis mappers and MySQL are
   exercised. A test failure blocks the job.
6. Confirms the old backend code never inserted values into the added
   probe field. Credentials, users and all records are synthetic test data.

The script `app/scripts/verify-expanded-backend-compatibility.sh`
will refuse non-CI execution and any unexpected schema name. The MySQL
service is localhost-only to that ephemeral runner. No production IP,
credential, SSH identity, SQL dump or file transfer is used.

## Limitations, stated explicitly

These are Spring Boot API **MockMvc** integration tests compiled from two
source checkouts. They do **not** start the old production JAR and candidate
JAR as separately managed processes, and they do not prove historical
production JAR/Web front-end compatibility, real HTTP networking, completed
media persistence, migration of real private rows, or production latency.

Furthermore, `main` changes between runs; it is a recorded repository
baseline, **not** independently attested running release. Since ENG-03D
adds no business-code change and no production migration, a successful
candidate result simply means both revisions can operate on an extra
nullable finance column in fresh synthetic schemas.

Before production migration approval, it remains mandatory to obtain
the exact **deployed** application and intended release artifacts, restore
a real approved backup to a **physically isolated** environment, verify
full private-row and ownership preservation, run authenticated old/new
JAR/API smoke tests against the same expanded restored schema with
cross-user boundaries, and review metadata-lock limits with production
DBA approval. An application-only rollback must be proven with the
*actual previous* binary. See [ENG-03C gates](eng-03c-controller-readiness.md).

## Production protection

This stage changes only the **test runner**, its CI job and this document.
It changes no Flyway SQL or migration policy, no root-owned deployment
controller or installed manifest, and no production credentials, services,
data or host. The existing `create-empty` policy continues to reject
`ALTER TABLE` from versioned release packages. ENG-03A/B/C PRs #96–98
remain prerequisites, and this PR must stay in Draft until independently
reviewed.
