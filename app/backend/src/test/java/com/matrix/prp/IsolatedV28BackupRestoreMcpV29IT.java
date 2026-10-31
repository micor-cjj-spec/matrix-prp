package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Map;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;

/**
 * Synthetic V28 MySQL dump/restore and additive V29 upgrade on a separate
 * disposable MySQL 8.4 container and Docker volume. Never target user data.
 *
 * Two GitHub-runner-only phases:
 *  seed:         prepare fully migrated synthetic V28 SOURCE with owner data.
 *  verify_clone: independently compare restored CLONE, apply V29 only there.
 *
 * This is not a recovery rehearsal with the user's actual V2 database;
 * neither synthetic outcome nor GITHUB_ACTIONS grants live deployment approval.
 */
class IsolatedV28BackupRestoreMcpV29IT {
    private static final String SOURCE_URL =
        "jdbc:mysql://127.0.0.1:13310/prp_v28_recovery_ci"
            + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String CLONE_URL =
        "jdbc:mysql://127.0.0.1:13311/prp_v28_recovery_ci"
            + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String USER = "prp_ci";
    private final FlywayV28ToV29IT synthetic = new FlywayV28ToV29IT();

    private static String phase() {
        String step = System.getenv("PRP_CI_V28_RESTORE_PHASE");
        if (!"seed".equals(step) && !"verify_clone".equals(step)) {
            throw new SecurityException("UNKNOWN_DISPOSABLE_RESTORE_PHASE");
        }
        return step;
    }

    private static void guard() {
        // Full URL, CI runner, isolated compose credentials, and intended phase
        // are pinned before ANY JDBC connection / Flyway operation.
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"YES".equals(System.getenv("PRP_CI_V28_RESTORE_ONLY"))
                || !SOURCE_URL.equals(System.getenv("PRP_CI_V28_SOURCE_URL"))
                || !CLONE_URL.equals(System.getenv("PRP_CI_V28_CLONE_URL"))
                || !USER.equals(System.getenv("MATRIX_PRP_FLYWAY_DB_USER"))
                || System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD") == null
                || System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD").length() < 32
                || System.getenv("GITHUB_RUN_ID") == null
                || !System.getenv("GITHUB_RUN_ID").matches("[0-9]+")) {
            throw new SecurityException("DISPOSABLE_CI_V28_RESTORE_ONLY");
        }
        phase();
    }

    private static Connection connect(String url) throws Exception {
        if (!SOURCE_URL.equals(url) && !CLONE_URL.equals(url)) {
            throw new SecurityException("UNREVIEWED_DB_URL");
        }
        return DriverManager.getConnection(url, USER,
                System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"));
    }

    private static long count(String url, String sql) throws Exception {
        try (Connection c = connect(url);
             var s = c.createStatement();
             var r = s.executeQuery(sql)) {
            assertThat(r.next()).isTrue();
            return r.getLong(1);
        }
    }

    private static long tableCount(String url) throws Exception {
        return count(url, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'");
    }

    private void seed() throws Exception {
        assertThat(tableCount(SOURCE_URL)).isZero();
        Flyway existing = synthetic.flyway(SOURCE_URL, "28");
        assertThat(existing.migrate().migrationsExecuted).isEqualTo(28);
        assertThat(existing.validateWithResult().validationSuccessful).isTrue();
        synthetic.populateSyntheticV28(SOURCE_URL);
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='28' AND success=1")).isEqualTo(1);
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() "
                + "AND TABLE_NAME='prp_mcp_oidc_link_flows'")).isZero();
        assertThat(synthetic.preservedFingerprints(SOURCE_URL)).hasSize(8);
        assertThat(tableCount(CLONE_URL)).isZero();
        System.out.println("CI_SYNTHETIC_V28_SOURCE_POPULATED_FOR_RESTORE=YES");
        System.out.println("NO_REAL_V2_OR_PRODUCTION_DATA_USED=YES");
    }

    private void verifyClone() throws Exception {
        Flyway source = synthetic.flyway(SOURCE_URL, "28");
        Flyway restored = synthetic.flyway(CLONE_URL, "28");
        assertThat(source.validateWithResult().validationSuccessful).isTrue();
        assertThat(restored.validateWithResult().validationSuccessful).isTrue();

        Map<String, String> original = synthetic.preservedFingerprints(SOURCE_URL);
        assertThat(synthetic.preservedFingerprints(CLONE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);
        long beforeTables = tableCount(SOURCE_URL);
        assertThat(tableCount(CLONE_URL)).isEqualTo(beforeTables);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history"))
                .isEqualTo(28);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() "
                + "AND TABLE_NAME='prp_mcp_oidc_link_flows'")).isZero();

        Flyway next = synthetic.flyway(CLONE_URL, null);
        assertThat(next.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(next.validateWithResult().validationSuccessful).isTrue();

        // A new additive OIDC state table on CLONE only; no changes to
        // any of the preexisting business rows or V1-V28 Flyway checksums.
        assertThat(tableCount(CLONE_URL)).isEqualTo(beforeTables + 1);
        assertThat(tableCount(SOURCE_URL)).isEqualTo(beforeTables);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history"))
                .isEqualTo(29);
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM flyway_schema_history"))
                .isEqualTo(28);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE installed_rank=29 AND version='29' "
                + "AND script='V29__mcp_first_party_oidc_link_flows.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() "
                + "AND TABLE_NAME='prp_mcp_oidc_link_flows'")).isZero();
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() "
                + "AND TABLE_NAME='prp_mcp_oidc_link_flows'")).isEqualTo(1);
        assertThat(count(CLONE_URL,
                "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                + "WHERE CONSTRAINT_SCHEMA=DATABASE() "
                + "AND CONSTRAINT_NAME='fk_prp_mcp_oidc_flow_owner'")).isEqualTo(1);

        // The restored new table must accept the verified synthetic owner,
        // but refuse an orphan owner in this real disposable MySQL engine.
        synthetic.insert(CLONE_URL, "INSERT INTO prp_mcp_oidc_link_flows "
                + "(state_hash,user_id,code_verifier,oidc_nonce,expires_at) "
                + "VALUES(?,?,?,?,DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                "d".repeat(64), 928001L, "ci-only-code-verifier", "ci-only-nonce");
        assertThrows(SQLException.class, () ->
                synthetic.insert(CLONE_URL, "INSERT INTO prp_mcp_oidc_link_flows "
                    + "(state_hash,user_id,code_verifier,oidc_nonce,expires_at) "
                    + "VALUES(?,?,?,?,DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                    "e".repeat(64), 999999L, "ci-only-code-verifier", "ci-only-nonce"));

        assertThat(synthetic.preservedFingerprints(CLONE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);
        assertThat(synthetic.preservedFingerprints(SOURCE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);
        assertThat(source.validateWithResult().validationSuccessful).isTrue();
        assertThat(next.migrate().migrationsExecuted).isZero();
        System.out.println("CI_SYNTHETIC_V28_ARCHIVE_RESTORED_BYTE_PARITY=PASS");
        System.out.println("CI_SYNTHETIC_V28_CLONE_V29_DATA_PRESERVED=PASS");
        System.out.println("CI_SYNTHETIC_ORIGINAL_V28_SOURCE_UNCHANGED=YES");
        System.out.println("CI_SYNTHETIC_V29_FK_REJECTS_ORPHAN=YES");
        System.out.println("NO_REAL_V2_OR_PRODUCTION_DATA_USED=YES");
        System.out.println("G0_B2_RELEASE_PERMITTED=NO");
    }

    @Test
    void guardedIsolatedV28RestoreAndV29CloneUpgrade() throws Exception {
        guard();
        if ("seed".equals(phase())) {
            seed();
        } else {
            verifyClone();
        }
    }
}
