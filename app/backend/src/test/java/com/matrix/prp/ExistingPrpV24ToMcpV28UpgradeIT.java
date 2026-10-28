package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;

/**
 * Integration review ONLY. Stages genuine V1-V24 Flyway migrations, inserts
 * synthetic "existing" PRP users/tasks/finance/video/vocal records, then
 * upgrades the SAME disposable populated database to V28. No Spring app,
 * HTTP, production backup, real owner credentials or live migration.
 *
 * A strict GitHub-runner environment + exact loopback JDBC schema guard is
 * checked BEFORE Flyway creates any tables or this test inserts any rows.
 */
class ExistingPrpV24ToMcpV28UpgradeIT {
    private static final String SCHEMA = "matrix_prp_upgrade_ci";
    private static final String URL =
        "jdbc:mysql://127.0.0.1:13308/" + SCHEMA
        + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai";
    private static final long ALICE = 12001L;
    private static final long BOB = 12002L;
    private static final Map<String, String> BUSINESS_SNAPSHOTS = Map.of(
        "prp_users",
            "SELECT id,username,display_name,is_admin,enabled FROM prp_users "
            + "WHERE id IN (12001,12002) ORDER BY id",
        "prp_tasks",
            "SELECT id,user_id,module_code,title,status,deleted FROM prp_tasks ORDER BY id",
        "prp_finance_transactions",
            "SELECT id,user_id,type,amount,category,deleted "
            + "FROM prp_finance_transactions ORDER BY id",
        "prp_video_assets",
            "SELECT id,user_id,title,storage_key FROM prp_video_assets ORDER BY id",
        "prp_vocal_songs",
            "SELECT id,user_id,title,status FROM prp_vocal_songs ORDER BY id"
    );
    private static final Set<String> EXPECTED_ADDITIONAL_TABLES = Set.of(
        "prp_mcp_write_drafts",
        "prp_mcp_client_grants",
        "prp_mcp_identity_links",
        "prp_mcp_link_tickets",
        "prp_mcp_oidc_link_flows"
    );

    private static void assertDisposableOnly() {
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"YES".equals(System.getenv("PRP_CI_DISPOSABLE_UPGRADE_ONLY"))
                || !URL.equals(System.getenv("MATRIX_PRP_DB_URL"))
                || !"prp_upgrade_ci".equals(System.getenv("MATRIX_PRP_DB_USER"))
                || System.getenv("MATRIX_PRP_DB_PASSWORD") == null
                || System.getenv("MATRIX_PRP_DB_PASSWORD").length() < 32) {
            throw new SecurityException("CI_DISPOSABLE_V24_UPGRADE_ONLY");
        }
    }

    private static String password() { return System.getenv("MATRIX_PRP_DB_PASSWORD"); }

    private static Flyway flyway(MigrationVersion target) {
        var builder = Flyway.configure().dataSource(URL, "prp_upgrade_ci", password())
            .locations("classpath:db/migration")
            .baselineOnMigrate(false)
            .cleanDisabled(true)
            .validateOnMigrate(true);
        if (target != null) builder.target(target);
        return builder.load();
    }

    private static void execute(Connection conn, String sql, Object... args) throws SQLException {
        try (PreparedStatement s = conn.prepareStatement(sql)) {
            for (int i = 0; i < args.length; i++) s.setObject(i + 1, args[i]);
            assertThat(s.executeUpdate()).isEqualTo(1);
        }
    }

    private static int count(Connection conn, String sql, Object... args) throws SQLException {
        try (PreparedStatement s = conn.prepareStatement(sql)) {
            for (int i = 0; i < args.length; i++) s.setObject(i + 1, args[i]);
            try (ResultSet rs = s.executeQuery()) {
                assertThat(rs.next()).isTrue();
                return rs.getInt(1);
            }
        }
    }

    private static String digest(Connection conn, String sql) throws Exception {
        MessageDigest d = MessageDigest.getInstance("SHA-256");
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            int columns = rs.getMetaData().getColumnCount();
            while (rs.next()) {
                for (int i = 1; i <= columns; i++) {
                    Object value = rs.getObject(i);
                    d.update((value == null ? "<NULL>" : value.toString())
                        .getBytes(StandardCharsets.UTF_8));
                    d.update((byte) 0x1f);
                }
                d.update((byte) 0x0a);
            }
        }
        return HexFormat.of().formatHex(d.digest());
    }

    private static Map<String, String> snapshots(Connection conn) throws Exception {
        Map<String, String> values = new LinkedHashMap<>();
        for (var entry : BUSINESS_SNAPSHOTS.entrySet())
            values.put(entry.getKey(), digest(conn, entry.getValue()));
        return values;
    }

    private static Set<String> tableNames(Connection conn) throws SQLException {
        Set<String> names = new LinkedHashSet<>();
        try (PreparedStatement s = conn.prepareStatement("SHOW FULL TABLES WHERE Table_type='BASE TABLE'");
             ResultSet rs = s.executeQuery()) {
            while (rs.next()) names.add(rs.getString(1));
        }
        return names;
    }

    private static void seedOldData(Connection conn) throws SQLException {
        for (long owner : new long[]{ALICE, BOB}) {
            execute(conn, "INSERT INTO prp_users(id,username,display_name,password_hash,is_admin,enabled) "
                + "VALUES(?,?,?,?,0,1)", owner, "ci_upgrade_" + owner,
                "Synthetic owner " + owner, "NOT_A_REAL_LOGIN_CREDENTIAL");
        }
        for (int i = 0; i < 24; i++) {
            execute(conn, "INSERT INTO prp_tasks(user_id,module_code,title,description,priority,"
                + "status,created_at,updated_at,deleted) "
                + "VALUES(?,'work',?,'synthetic record','low','todo',NOW(6),NOW(6),0)",
                ALICE, "CI pre-V25 A " + i);
        }
        for (int i = 0; i < 3; i++) {
            execute(conn, "INSERT INTO prp_tasks(user_id,module_code,title,description,priority,"
                + "status,created_at,updated_at,deleted) "
                + "VALUES(?,'work',?,'synthetic record','medium','todo',NOW(6),NOW(6),0)",
                BOB, "CI pre-V25 B " + i);
        }
        execute(conn, "INSERT INTO prp_finance_transactions(user_id,type,amount,category,"
            + "account,merchant,note,transaction_date,created_at,updated_at,deleted) "
            + "VALUES(?,'expense',12.50,'synthetic','cash','','ci-only',CURRENT_DATE(),NOW(6),NOW(6),0)",
            ALICE);
        execute(conn, "INSERT INTO prp_video_assets(user_id,title,storage_key,size_bytes) "
            + "VALUES(?,'CI old video',?,128)", BOB, UUID.randomUUID().toString());
        execute(conn, "INSERT INTO prp_vocal_songs(user_id,title,artist) "
            + "VALUES(?,'CI old vocal song','synthetic')", ALICE);
    }

    @Test
    void seededMainV24DataSurvivesAdditiveV25ToV28WithoutChangingOwnership() throws Exception {
        assertDisposableOnly();
        try (Connection conn = DriverManager.getConnection(URL, "prp_upgrade_ci", password())) {
            assertThat(count(conn, "SELECT COUNT(*) FROM information_schema.schemata "
                + "WHERE schema_name=?", SCHEMA)).isEqualTo(1);
            try (PreparedStatement p = conn.prepareStatement("SELECT DATABASE()");
                 ResultSet r = p.executeQuery()) {
                assertThat(r.next()).isTrue();
                assertThat(r.getString(1)).isEqualTo(SCHEMA);
            }
            assertThat(tableNames(conn)).isEmpty();

            // Same classpath SQL files, deliberately restricted to the
            // original main V24 target before any newer MCP migrations.
            var first = flyway(MigrationVersion.fromVersion("24")).migrate();
            assertThat(first.migrationsExecuted).isEqualTo(24);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE success=1 AND version IS NOT NULL")).isEqualTo(24);
            seedOldData(conn);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks WHERE user_id=?", ALICE))
                .isEqualTo(24);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks WHERE user_id=?", BOB))
                .isEqualTo(3);
            Map<String, String> before = snapshots(conn);
            String oldHistory = digest(conn, "SELECT version,script,checksum,success "
                + "FROM flyway_schema_history WHERE version BETWEEN 1 AND 24 ORDER BY installed_rank");
            Set<String> oldTables = tableNames(conn);
            for (String mcpTable : EXPECTED_ADDITIONAL_TABLES)
                assertThat(oldTables).doesNotContain(mcpTable);

            var second = flyway(null).migrate();
            assertThat(second.migrationsExecuted).isEqualTo(4);
            flyway(null).validate();
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE success=1 AND version IS NOT NULL")).isEqualTo(28);
            assertThat(digest(conn, "SELECT version,script,checksum,success "
                + "FROM flyway_schema_history WHERE version BETWEEN 1 AND 24 ORDER BY installed_rank"))
                .isEqualTo(oldHistory);
            assertThat(snapshots(conn)).containsExactlyInAnyOrderEntriesOf(before);

            Set<String> newTables = tableNames(conn);
            Set<String> additions = new LinkedHashSet<>(newTables);
            additions.removeAll(oldTables);
            assertThat(additions).containsExactlyInAnyOrderElementsOf(EXPECTED_ADDITIONAL_TABLES);
            assertThat(newTables).containsAll(oldTables);

            // Existing owner IDs are valid FK targets for the new MCP
            // grant/link tables; no direct production task-bridge needed.
            execute(conn, "INSERT INTO prp_mcp_client_grants(user_id,client_id,scopes,status) "
                + "VALUES(?,'ci-chatgpt-client','prp.tasks.read','ACTIVE')", ALICE);
            execute(conn, "INSERT INTO prp_mcp_identity_links(issuer,subject,user_id) "
                + "VALUES('https://issuer.invalid','synthetic-owner-a',?)", ALICE);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_mcp_client_grants "
                + "WHERE user_id=? AND scopes='prp.tasks.read'", ALICE)).isEqualTo(1);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_mcp_identity_links "
                + "WHERE user_id=? AND subject='synthetic-owner-a'", ALICE)).isEqualTo(1);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks WHERE user_id=? LIMIT 20", BOB))
                .isEqualTo(3);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks WHERE user_id=?", ALICE))
                .isEqualTo(24);
            assertThat(snapshots(conn)).containsExactlyInAnyOrderEntriesOf(before);
        }
        System.out.println("PASS CI_SYNTHETIC_POPULATED_V24_TO_V28_DATA_PRESERVED=YES");
        System.out.println("NO_PRODUCTION_SCHEMA_OR_USER_TASKS_ACCESSED=YES");
    }
}
