# PRP ENG-01 / ENG-02: regression-test improvement plan

## First-stage implementation

- The backend `mvn verify` phase generates `target/site/jacoco/index.html` and `jacoco.xml`.
- Pull request CI keeps its existing compile, unit, real-MySQL, migration, deployment-safety and frontend checks. `backend-tests` additionally uploads a coverage artifact (14-day retention).
- The existing Surefire JVM memory ceiling is preserved: `@{argLine}` expands the JaCoCo agent while retaining `-Xmx160m` and `-XX:MaxMetaspaceSize=128m`.
- There is intentionally **no repository-wide percentage gate yet**. Record baseline coverage first; then introduce targeted thresholds on modified business components.
- Regression protection is added separately for finance bill import and AI meal-draft authorization. No production data, schemas or deployment-controller permissions change.

## Commands

```bash
cd app/backend
./mvnw -B verify
# Review target/site/jacoco/index.html and the CI artifact
```

## Next test-infrastructure steps (not claimed to be complete)

1. Add Vitest with a committed, reproducible lockfile and targeted Vue composable tests.
2. Add Playwright against an isolated test deployment and synthetic accounts; never run data-mutating browser tests on production.
3. Introduce a dedicated CI quality gate for **changed** business logic only after a measured baseline, while retaining all permission, migration and production-preservation gates.
4. Add boundary tests for finance partial account mappings, duplicate source IDs, draft expiry, tenant isolation and confirmation idempotency.

## Release rule

Do not merge an engineering-test branch until the complete required CI suite passes. Do not use this work to loosen SSH, database migration or backup safety gates.
