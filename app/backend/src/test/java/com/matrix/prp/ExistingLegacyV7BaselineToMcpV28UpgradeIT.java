package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;

/**
 * DISPOSABLE CI ONLY: independently reproduces legacy V7 baseline -> V24 ->
 * V28 using real MySQL and synthetic owner/tasks. Never touches a production
 * schema, backups or an existing test/staging volume.
 *
 * Starting from fresh V1..V7 schema and deleting ONLY the disposable Flyway
 * history simulates historical manual DDL before explicitly baselining at V7.
 * This does NOT attest the real prebaseline V1..V7 production DDL.
 */
class ExistingLegacyV7BaselineToMcpV28UpgradeIT {
    private static final String SCHEMA = "matrix_prp_upgrade_ci";
    private static final String URL =
        "jdbc:mysql://127.0.0.1:13308/" + SCHEMA
            + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai";
    private static final String USER = "prp_upgrade_ci";

    private static void assertDisposableOnly() {
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"YES".equals(System.getenv("PRP_CI_DISPOSABLE_LEGACY_BASELINE_ONLY"))
                || !URL.equals(System.getenv("MATRIX_PRP_DB_URL"))
                || !USER.equals(System.getenv("MATRIX_PRP_DB_USER"))
                || System.getenv("MATRIX_PRP_DB_PASSWORD") == null
                || System.getenv("MATRIX_PRP_DB_PASSWORD").length() < 32) {
            throw new SecurityException("CI_DISPOSABLE_LEGACY_BASELINE_ONLY");
        }
    }

    private static String password() {
        return System.getenv("MATRIX_PRP_DB_PASSWORD");
    }

    private static Flyway flyway(String target) {
        var config = Flyway.configure()
            .dataSource(URL, USER, password())
            .locations("classpath:db/migration")
            .baselineVersion("7")
            .baselineOnMigrate(false)
            .cleanDisabled(true)
            .validateOnMigrate(true);
        if (target != null) config.target(MigrationVersion.fromVersion(target));
        return config.load();
    }

    private static int count(Connection conn, String sql) throws Exception {
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            assertThat(rs.next()).isTrue();
            return rs.getInt(1);
        }
    }

    private static void insert(Connection conn, String sql, Object... args) throws Exception {
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            for (int i = 0; i < args.length; ++i) ps.setObject(i + 1, args[i]);
            assertThat(ps.executeUpdate()).isEqualTo(1);
        }
    }

    private static String fingerprint(Connection conn, String sql) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (PreparedStatement ps = conn.prepareStatement(sql);
             ResultSet rs = ps.executeQuery()) {
            int columns = rs.getMetaData().getColumnCount();
            while (rs.next()) {
                for (int col = 1; col <= columns; ++col) {
                    Object value = rs.getObject(col);
                    hash.update((value == null ? "<NULL>" : value.toString())
                        .getBytes(StandardCharsets.UTF_8));
                    hash.update((byte) 0x1f);
                }
                hash.update((byte) 0x0a);
            }
        }
        return HexFormat.of().formatHex(hash.digest());
    }

    private static Map<String, String> snapshots(Connection conn) throws Exception {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("users", fingerprint(conn,
            "SELECT id,username,display_name,is_admin,enabled FROM prp_users "
                + "WHERE id IN (12001,12002) ORDER BY id"));
        result.put("tasks", fingerprint(conn,
            "SELECT id,user_id,module_code,title,status,deleted FROM prp_tasks ORDER BY id"));
        result.put("finance", fingerprint(conn,
            "SELECT id,user_id,type,amount,category,deleted "
                + "FROM prp_finance_transactions ORDER BY id"));
        return result;
    }

    private static String sourceCrcAggregateSql() throws Exception {
        // Checked-out candidate SQL only. This Python generator has no DB
        // client, secrets, business data, imports or network calls.
        Process process = new ProcessBuilder(
            "python3", "../deploy/mcp-staging/production_v24_checksum_query.py",
            "--ci-disposable-schema"
        ).start();
        boolean finished = process.waitFor(10, TimeUnit.SECONDS);
        if (!finished) {
            process.destroyForcibly();
            throw new SecurityException("CI_V24_SOURCE_CRC_QUERY_GENERATOR_TIMEOUT");
        }
        if (process.exitValue() != 0)
            throw new SecurityException("CI_V24_SOURCE_CRC_QUERY_GENERATOR_FAILED");
        String sql = new String(process.getInputStream().readAllBytes(),
            StandardCharsets.UTF_8).trim();
        assertThat(sql).startsWith("WITH expected AS (");
        assertThat(sql).endsWith(";");
        return sql;
    }

    private static void assertSourceCrcAggregate(Connection conn, String sql,
            int expectedHistory, int expectedSql, String verdict) throws Exception {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(sql)) {
            assertThat(rs.next()).isTrue();
            assertThat(rs.getString("schema_match")).isEqualTo("YES");
            assertThat(rs.getInt("history_rows")).isEqualTo(expectedHistory);
            assertThat(rs.getInt("baseline_rows_matched")).isEqualTo(1);
            assertThat(rs.getInt("observed_sql_rows")).isEqualTo(expectedSql);
            assertThat(rs.getInt("source_sql_rows_matched")).isEqualTo(17);
            assertThat(rs.getString("decision")).isEqualTo(verdict);
            assertThat(rs.getString("deployment_permitted")).isEqualTo("NO");
            assertThat(rs.next()).isFalse();
        }
    }

    @Test
    void legacyV7FlywayBaselinePreservesExistingOwnersAndTasksThroughV28()
            throws Exception {
        assertDisposableOnly();
        try (Connection conn = DriverManager.getConnection(URL, USER, password())) {
            assertThat(count(conn, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE()")).isZero();

            // The first 7 migrations create *only* a disposable legacy-equivalent
            // schema. Remove its disposable Flyway history to model the historical
            // manual 001..007 setup. No real MySQL volume or row is reachable.
            assertThat(flyway("7").migrate().migrationsExecuted).isEqualTo(7);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history"))
                .isEqualTo(7);
            try (Statement stmt = conn.createStatement()) {
                stmt.execute("DROP TABLE flyway_schema_history");
            }
            assertThat(count(conn, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_name='flyway_schema_history'"))
                .isZero();
            flyway("24").baseline();
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE installed_rank=1 AND version='7' AND type='BASELINE' "
                + "AND script='<< Flyway Baseline >>' AND checksum IS NULL AND success=1"))
                .isEqualTo(1);

            assertThat(flyway("24").migrate().migrationsExecuted).isEqualTo(17);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history"))
                .isEqualTo(18);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE installed_rank=18 AND version='24' AND type='SQL' "
                + "AND script='V24__vocal_song_library_and_assignments.sql' AND success=1"))
                .isEqualTo(1);

            // Actual MySQL executes the *same* fixed aggregate SELECT intended
            // for later operator-only production metadata review. No raw CRCs
            // are selected, copied, logged or sent to CI artifacts.
            String aggregateSql = sourceCrcAggregateSql();
            assertSourceCrcAggregate(conn, aggregateSql, 18, 17,
                "SOURCE_CRC_MATCH_REVIEW_ONLY");

            for (long owner : new long[]{12001L, 12002L}) {
                insert(conn, "INSERT INTO prp_users(id,username,display_name,password_hash,"
                    + "is_admin,enabled) VALUES(?,?,?,?,0,1)",
                    owner, "ci_legacy_" + owner, "CI owner " + owner, "SYNTHETIC_NOT_REAL");
                insert(conn, "INSERT INTO prp_tasks(user_id,module_code,title,description,"
                    + "priority,status,created_at,updated_at,deleted) "
                    + "VALUES(?,'work',?,'synthetic','low','todo',NOW(6),NOW(6),0)",
                    owner, "CI task " + owner);
            }
            insert(conn, "INSERT INTO prp_finance_transactions(user_id,type,amount,"
                + "category,account,merchant,note,transaction_date,created_at,updated_at,deleted) "
                + "VALUES(?,'expense',12.50,'ci','cash','','synthetic',CURRENT_DATE(),"
                + "NOW(6),NOW(6),0)", 12001L);

            Map<String, String> before = snapshots(conn);
            String historyBefore = fingerprint(conn,
                "SELECT installed_rank,version,type,script,checksum,success "
                    + "FROM flyway_schema_history ORDER BY installed_rank");

            assertThat(flyway(null).migrate().migrationsExecuted).isEqualTo(4);
            flyway(null).validate();
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(22);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE installed_rank=1 AND version='7' AND type='BASELINE' "
                + "AND checksum IS NULL AND success=1")).isEqualTo(1);
            assertThat(count(conn, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE installed_rank=22 AND version='28' AND type='SQL' AND success=1"))
                .isEqualTo(1);
            assertThat(fingerprint(conn,
                "SELECT installed_rank,version,type,script,checksum,success "
                    + "FROM flyway_schema_history WHERE installed_rank<=18 "
                    + "ORDER BY installed_rank")).isEqualTo(historyBefore);
            assertThat(snapshots(conn)).containsExactlyInAnyOrderEntriesOf(before);
            // V28 is not the expected live V24 state. The same fixed
            // production V24 preflight must now fail closed in this
            // otherwise healthy disposable V28 database.
            assertSourceCrcAggregate(conn, aggregateSql, 22, 21,
                "BLOCKED_OR_UNVERIFIED");
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks "
                + "WHERE user_id=12001")).isEqualTo(1);
            assertThat(count(conn, "SELECT COUNT(*) FROM prp_tasks "
                + "WHERE user_id=12002")).isEqualTo(1);
        }
        System.out.println("PASS CI_DISPOSABLE_REAL_MYSQL_V7_BASELINE_V24_V28=YES");
        System.out.println("CI_LEGACY_SYNTHETIC_OWNER_TASKS_AND_FINANCE_PRESERVED=YES");
        System.out.println("NO_PRODUCTION_DATA_OR_BACKUP_ACCESSED=YES");
    }
}
