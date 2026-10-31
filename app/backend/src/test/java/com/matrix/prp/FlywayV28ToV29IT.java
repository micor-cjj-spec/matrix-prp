package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/**
 * Isolated GitHub CI MySQL 8.4 ONLY. Tests additive V28->V29 against a
 * populated *synthetic* V28 schema. This is NOT an actual V2 database restore,
 * a production-data compatibility certification, or G0/B2 authorization.
 */
@EnabledIfEnvironmentVariable(named = "MATRIX_PRP_FLYWAY_V28_V29_URL", matches = "jdbc:mysql:.+")
class FlywayV28ToV29IT {
    private static final String DATABASE_URL =
            "jdbc:mysql://127.0.0.1:3306/prp_flyway_v28_v29?useSSL=false&allowPublicKeyRetrieval=true";
    private static final long OWNER_A = 928001L;
    private static final long OWNER_B = 928002L;
    private static final Map<String, String> PRESERVED_QUERIES = Map.of(
        "owners", "SELECT id,username,display_name,enabled FROM prp_users ORDER BY id",
        "tasks", "SELECT id,user_id,module_code,title,status,deleted FROM prp_tasks ORDER BY id",
        "finance", "SELECT id,user_id,type,amount,category,deleted "
                + "FROM prp_finance_transactions ORDER BY id",
        "grants", "SELECT user_id,client_id,scopes,status,created_at,updated_at "
                + "FROM prp_mcp_client_grants ORDER BY user_id,client_id",
        "leases", "SELECT user_id,client_id,expires_at,created_at "
                + "FROM prp_mcp_pairing_grant_leases ORDER BY user_id,client_id",
        "links", "SELECT issuer,subject,user_id,linked_at "
                + "FROM prp_mcp_identity_links ORDER BY issuer,subject",
        "tickets", "SELECT ticket_hash,user_id,client_id,expires_at,consumed_at "
                + "FROM prp_mcp_link_tickets ORDER BY ticket_hash",
        "history", "SELECT installed_rank,version,script,checksum,success "
                + "FROM flyway_schema_history WHERE installed_rank<=28 ORDER BY installed_rank"
    );

    private void guard(String url) {
        // Never change these exact CI-only guards to a caller-controlled URL.
        assertThat(url).as("one disposable CI-only database").isEqualTo(DATABASE_URL);
        assertThat(System.getenv("GITHUB_ACTIONS")).as("ephemeral GitHub CI runner only")
                .isEqualTo("true");
        assertThat(System.getenv("RUNNER_OS")).isEqualTo("Linux");
        assertThat(System.getenv("MATRIX_PRP_FLYWAY_DB_USER")).isEqualTo("prp_ci");
        assertThat(System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"))
                .isEqualTo("ci-only-password");
    }

    private Connection connect(String url) throws Exception {
        return DriverManager.getConnection(url,
                System.getenv("MATRIX_PRP_FLYWAY_DB_USER"),
                System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"));
    }

    long count(String url, String query) throws Exception {
        try (Connection c = connect(url);
             Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(query)) {
            assertThat(rs.next()).isTrue();
            return rs.getLong(1);
        }
    }

    void insert(String url, String query, Object... parameters) throws Exception {
        try (Connection c = connect(url);
             PreparedStatement statement = c.prepareStatement(query)) {
            for (int i = 0; i < parameters.length; i++) {
                statement.setObject(i + 1, parameters[i]);
            }
            assertThat(statement.executeUpdate()).isEqualTo(1);
        }
    }

    private String fingerprint(String url, String query) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (Connection c = connect(url);
             PreparedStatement statement = c.prepareStatement(query);
             ResultSet rows = statement.executeQuery()) {
            int columns = rows.getMetaData().getColumnCount();
            while (rows.next()) {
                for (int index = 1; index <= columns; index++) {
                    String value = rows.getString(index);
                    digest.update((value == null ? "<NULL>" : value)
                            .getBytes(StandardCharsets.UTF_8));
                    digest.update((byte) 0x1f);
                }
                digest.update((byte) 0x0a);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    Map<String, String> preservedFingerprints(String url) throws Exception {
        Map<String, String> snapshots = new LinkedHashMap<>();
        for (var entry : PRESERVED_QUERIES.entrySet()) {
            snapshots.put(entry.getKey(), fingerprint(url, entry.getValue()));
        }
        return snapshots;
    }

    Flyway flyway(String url, String target) {
        var config = Flyway.configure()
                .dataSource(url, System.getenv("MATRIX_PRP_FLYWAY_DB_USER"),
                        System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"))
                .locations("classpath:db/migration")
                .cleanDisabled(true)
                .validateOnMigrate(true);
        if (target != null) {
            config.target(MigrationVersion.fromVersion(target));
        }
        return config.load();
    }

    void populateSyntheticV28(String url) throws Exception {
        for (long owner : new long[] {OWNER_A, OWNER_B}) {
            insert(url, "INSERT INTO prp_users "
                    + "(id,username,display_name,password_hash,is_admin,enabled) "
                    + "VALUES(?,?,?,'CI_ONLY_FAKE_PASSWORD_HASH',0,1)",
                    owner, "ci_mcp_v29_" + owner, "Synthetic owner " + owner);
            insert(url, "INSERT INTO prp_tasks "
                    + "(user_id,module_code,title,description,priority,status,"
                    + "created_at,updated_at,deleted) "
                    + "VALUES(?,'work',?,'ci-only','low','todo',NOW(6),NOW(6),0)",
                    owner, "Synthetic task " + owner);
            insert(url, "INSERT INTO prp_mcp_client_grants "
                    + "(user_id,client_id,scopes,status) "
                    + "VALUES(?,'ci-synthetic-client','prp.tasks.read','ACTIVE')", owner);
        }
        insert(url, "INSERT INTO prp_finance_transactions "
                + "(user_id,type,amount,category,account,merchant,note,"
                + "transaction_date,created_at,updated_at,deleted) "
                + "VALUES(?,'expense',4.25,'synthetic','cash','','ci-only',"
                + "CURRENT_DATE(),NOW(6),NOW(6),0)", OWNER_A);
        insert(url, "INSERT INTO prp_mcp_pairing_grant_leases "
                + "(user_id,client_id,expires_at) "
                + "VALUES(?,'ci-synthetic-client',DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                OWNER_A);
        insert(url, "INSERT INTO prp_mcp_identity_links "
                + "(issuer,subject,user_id) "
                + "VALUES('https://issuer.invalid/ci','synthetic-subject',?)", OWNER_A);
        insert(url, "INSERT INTO prp_mcp_link_tickets "
                + "(ticket_hash,user_id,client_id,expires_at) "
                + "VALUES(?,?,?,DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                "a".repeat(64), OWNER_B, "ci-synthetic-client");
        assertThat(count(url, "SELECT COUNT(*) FROM prp_users WHERE id IN (928001,928002)"))
                .isEqualTo(2);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_tasks "
                + "WHERE user_id IN (928001,928002)")).isEqualTo(2);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_mcp_pairing_grant_leases")).isEqualTo(1);
    }

    @Test
    void upgradesPopulatedV28WithoutChangingOriginalRowsOrFlywayHistory() throws Exception {
        String url = System.getenv("MATRIX_PRP_FLYWAY_V28_V29_URL");
        guard(url);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE()")).isZero();

        Flyway old = flyway(url, "28");
        assertThat(old.migrate().success).isTrue();
        assertThat(old.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='28' AND script='V28__mcp_temporary_client_grant_expiry.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() "
                + "AND table_name='prp_mcp_pairing_grant_leases'")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(28);
        populateSyntheticV28(url);
        Map<String, String> before = preservedFingerprints(url);
        long beforeTables = count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_type='BASE TABLE'");
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_name='prp_mcp_oidc_link_flows'"))
                .isZero();

        Flyway next = flyway(url, null);
        assertThat(next.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(next.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(29);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='29' AND script='V29__mcp_first_party_oidc_link_flows.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_type='BASE TABLE'"))
                .isEqualTo(beforeTables + 1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_name='prp_mcp_oidc_link_flows'"))
                .isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.referential_constraints "
                + "WHERE constraint_schema=DATABASE() "
                + "AND constraint_name='fk_prp_mcp_oidc_flow_owner'")).isEqualTo(1);
        assertThat(preservedFingerprints(url)).containsExactlyInAnyOrderEntriesOf(before);

        // Check the new table's foreign key in the real CI MySQL, not only its DDL string.
        insert(url, "INSERT INTO prp_mcp_oidc_link_flows "
                + "(state_hash,user_id,code_verifier,oidc_nonce,expires_at) "
                + "VALUES(?,?,?,?,DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                "b".repeat(64), OWNER_A, "ci-only-pkce-verifier", "ci-only-nonce");
        assertThat(count(url, "SELECT COUNT(*) FROM prp_mcp_oidc_link_flows "
                + "WHERE user_id=928001 AND consumed_at IS NULL")).isEqualTo(1);
        assertThrows(SQLException.class, () -> insert(url,
                "INSERT INTO prp_mcp_oidc_link_flows "
                + "(state_hash,user_id,code_verifier,oidc_nonce,expires_at) "
                + "VALUES(?,?,?,?,DATE_ADD(NOW(),INTERVAL 10 MINUTE))",
                "c".repeat(64), 999999L, "ci-only-pkce-verifier", "ci-only-nonce"));
        assertThat(preservedFingerprints(url)).containsExactlyInAnyOrderEntriesOf(before);
        assertThat(next.migrate().migrationsExecuted).isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(29);
        System.out.println("CI_SYNTHETIC_POPULATED_V28_TO_V29_DATA_PRESERVATION=PASS");
        System.out.println("CI_SYNTHETIC_V29_OWNER_FOREIGN_KEY_ENFORCED=PASS");
        System.out.println("NO_LIVE_V2_OR_PRODUCTION_DATABASE_ACCESSED=YES");
        System.out.println("G0_B2_RELEASE_PERMITTED=NO");
    }
}
