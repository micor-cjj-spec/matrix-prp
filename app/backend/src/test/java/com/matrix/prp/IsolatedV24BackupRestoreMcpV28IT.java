package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;

/**
 * CI ONLY: two disposable, loopback-only MySQL 8.4 containers.
 * Phase seed builds an ACTUAL V7 baseline + V8..V24 using repo Flyway,
 * populates synthetic owners/tasks/finance/video/vocal. The CI workflow
 * then exports this full schema and restores into a separately named
 * container and volume. Phase verify_clone validates identical snapshots
 * and applies V25..V28 ONLY to the restored copy, checking source unchanged.
 *
 * No live PRP data, production DB, customer backups, production clients,
 * Keycloak, Nginx, production SSH, or G0/B2 receipts are ever accessed.
 */
class IsolatedV24BackupRestoreMcpV28IT {
    private static final String SCHEMA = "matrix_prp_upgrade_ci";
    private static final String SOURCE_URL =
        "jdbc:mysql://127.0.0.1:13308/" + SCHEMA
            + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai";
    private static final String CLONE_URL =
        "jdbc:mysql://127.0.0.1:13309/" + SCHEMA
            + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai";
    private static final Set<String> NEW_TABLES = Set.of(
        "prp_mcp_write_drafts", "prp_mcp_client_grants",
        "prp_mcp_identity_links", "prp_mcp_link_tickets",
        "prp_mcp_pairing_grant_leases");
    private static final Map<String,String> QUERIES = Map.of(
        "owners", "SELECT id,username,display_name,enabled FROM prp_users ORDER BY id",
        "tasks", "SELECT id,user_id,module_code,title,status,deleted FROM prp_tasks ORDER BY id",
        "finance", "SELECT id,user_id,type,amount,category,deleted FROM prp_finance_transactions ORDER BY id",
        "video", "SELECT id,user_id,title,storage_key FROM prp_video_assets ORDER BY id",
        "vocal", "SELECT id,user_id,title,status FROM prp_vocal_songs ORDER BY id",
        "history", "SELECT installed_rank,version,type,script,checksum,success "
            + "FROM flyway_schema_history WHERE installed_rank<=18 ORDER BY installed_rank");

    private static void guard() {
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
            || !"Linux".equals(System.getenv("RUNNER_OS"))
            || !"YES".equals(System.getenv("PRP_CI_FULL_SCHEMA_RESTORE_ONLY"))
            || !SOURCE_URL.equals(System.getenv("PRP_CI_MYSQL_SOURCE_URL"))
            || !CLONE_URL.equals(System.getenv("PRP_CI_MYSQL_CLONE_URL"))
            || !"prp_upgrade_ci".equals(System.getenv("MATRIX_PRP_DB_USER"))
            || System.getenv("MATRIX_PRP_DB_PASSWORD") == null
            || System.getenv("MATRIX_PRP_DB_PASSWORD").length() < 32
            || !Set.of("seed", "verify_clone").contains(
                System.getenv("PRP_CI_FULL_SCHEMA_PHASE"))) {
            throw new SecurityException("DISPOSABLE_CI_FULL_SCHEMA_RESTORE_ONLY");
        }
    }
    private static String password() { return System.getenv("MATRIX_PRP_DB_PASSWORD"); }
    private static Connection conn(String url) throws Exception {
        return DriverManager.getConnection(url, "prp_upgrade_ci", password());
    }
    private static Flyway flyway(String url, String target) {
        var builder = Flyway.configure()
            .dataSource(url, "prp_upgrade_ci", password())
            .locations("classpath:db/migration")
            .baselineVersion("7")
            .baselineOnMigrate(false)
            .cleanDisabled(true)
            .validateOnMigrate(true);
        if (target != null) builder.target(MigrationVersion.fromVersion(target));
        return builder.load();
    }
    private static long count(Connection c, String query) throws Exception {
        try (Statement st=c.createStatement(); ResultSet r=st.executeQuery(query)) {
            assertThat(r.next()).isTrue();
            return r.getLong(1);
        }
    }
    private static void insert(Connection c, String sql, Object... args) throws Exception {
        try (PreparedStatement s=c.prepareStatement(sql)) {
            for (int i=0; i<args.length; i++) s.setObject(i+1,args[i]);
            assertThat(s.executeUpdate()).isEqualTo(1);
        }
    }
    private static String fingerprint(Connection c, String sql) throws Exception {
        var d=MessageDigest.getInstance("SHA-256");
        try (PreparedStatement s=c.prepareStatement(sql); ResultSet r=s.executeQuery()) {
            int cols=r.getMetaData().getColumnCount();
            while(r.next()) {
                for (int i=1; i<=cols; i++) {
                    String value=r.getString(i);
                    d.update((value==null ? "<NULL>" : value).getBytes(StandardCharsets.UTF_8));
                    d.update((byte)0x1f);
                }
                d.update((byte)0x0a);
            }
        }
        return HexFormat.of().formatHex(d.digest());
    }
    private static Map<String,String> fingerprints(Connection c) throws Exception {
        Map<String,String> result=new LinkedHashMap<>();
        for (var entry:QUERIES.entrySet())
            result.put(entry.getKey(),fingerprint(c,entry.getValue()));
        return result;
    }
    private static long baseTables(Connection c) throws Exception {
        return count(c,"SELECT COUNT(*) FROM information_schema.TABLES "
            + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'");
    }
    private static void assertV24(Connection c) throws Exception {
        assertThat(count(c,"SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(18);
        assertThat(count(c,"SELECT COUNT(*) FROM flyway_schema_history "
            + "WHERE installed_rank=1 AND version='7' AND type='BASELINE' "
            + "AND checksum IS NULL AND success=1")).isEqualTo(1);
        assertThat(count(c,"SELECT COUNT(*) FROM flyway_schema_history "
            + "WHERE type='SQL' AND success=1 AND CAST(version AS UNSIGNED) BETWEEN 8 AND 24")).isEqualTo(17);
        // Operator observed 57 visible InnoDB base tables in the real
        // production V24 schema. Enforce that the reviewed full V24
        // source builds the same count; this still does not prove DDL
        // and object privileges are identical to production.
        assertThat(baseTables(c)).isEqualTo(57);
        assertThat(count(c,"SELECT COUNT(*) FROM prp_tasks WHERE user_id=12001")).isEqualTo(24);
        assertThat(count(c,"SELECT COUNT(*) FROM prp_tasks WHERE user_id=12002")).isEqualTo(3);
        assertThat(count(c,"SELECT COUNT(*) FROM prp_finance_transactions")).isEqualTo(1);
        assertThat(count(c,"SELECT COUNT(*) FROM prp_video_assets")).isEqualTo(1);
        assertThat(count(c,"SELECT COUNT(*) FROM prp_vocal_songs")).isEqualTo(1);
    }
    private static void seed() throws Exception {
        try (Connection c=conn(SOURCE_URL)) {
            assertThat(baseTables(c)).isZero();
            assertThat(flyway(SOURCE_URL,"7").migrate().migrationsExecuted).isEqualTo(7);
            // Model a real V7-manually-baselined production source ONLY
            // on the brand-new explicitly CI-owned source schema.
            try (Statement st=c.createStatement()) {
                st.execute("DROP TABLE flyway_schema_history");
            }
            assertThat(flyway(SOURCE_URL,"24").baseline().successfullyBaselined).isTrue();
            assertThat(flyway(SOURCE_URL,"24").migrate().migrationsExecuted).isEqualTo(17);
            for (long owner:new long[]{12001L,12002L})
                insert(c,"INSERT INTO prp_users(id,username,display_name,password_hash,is_admin,enabled) "
                    +"VALUES(?,?,?,?,0,1)",owner,"ci_backup_"+owner,
                    "Synthetic owner "+owner,"SYNTHETIC_ONLY");
            for (int i=0;i<27;i++) {
                long owner=i<24 ? 12001L : 12002L;
                insert(c,"INSERT INTO prp_tasks(user_id,module_code,title,description,priority,"
                    +"status,created_at,updated_at,deleted) "
                    +"VALUES(?,'work',?,'synthetic fixture','low','todo',NOW(6),NOW(6),0)",
                    owner,"CI backup restore task "+i);
            }
            insert(c,"INSERT INTO prp_finance_transactions(user_id,type,amount,category,"
                +"account,merchant,note,transaction_date,created_at,updated_at,deleted) "
                +"VALUES(?,'expense',12.50,'synthetic','cash','','ci-fixture',"
                +"CURRENT_DATE(),NOW(6),NOW(6),0)",12001L);
            insert(c,"INSERT INTO prp_video_assets(user_id,title,storage_key,size_bytes) "
                +"VALUES(?,'CI synthetic video','synthetic-only-file',128)",12002L);
            insert(c,"INSERT INTO prp_vocal_songs(user_id,title,artist) "
                +"VALUES(?,'CI synthetic song','synthetic')",12001L);
            assertV24(c);
            assertThat(fingerprints(c)).hasSize(6);
        }
        System.out.println("CI_SYNTHETIC_TRUE_V7_BASELINE_V24_SOURCE_SEEDED=YES");
    }
    private static void verifyClone() throws Exception {
        try (Connection source=conn(SOURCE_URL); Connection clone=conn(CLONE_URL)) {
            assertV24(source);
            assertV24(clone);
            long beforeTables=baseTables(source);
            Map<String,String> original=fingerprints(source);
            assertThat(fingerprints(clone)).containsExactlyInAnyOrderEntriesOf(original);
            for (String name:NEW_TABLES)
                assertThat(count(clone,"SELECT COUNT(*) FROM information_schema.TABLES "
                    +"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"'")).isZero();
            assertThat(flyway(CLONE_URL,"28").migrate().migrationsExecuted).isEqualTo(4);
            flyway(CLONE_URL,"28").validate();
            assertThat(count(clone,"SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(22);
            assertThat(baseTables(clone)).isEqualTo(beforeTables+5);
            for (String name:NEW_TABLES) {
                assertThat(count(clone,"SELECT COUNT(*) FROM information_schema.TABLES "
                    +"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"'")).isEqualTo(1);
                assertThat(count(source,"SELECT COUNT(*) FROM information_schema.TABLES "
                    +"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+name+"'")).isZero();
            }
            assertThat(count(clone,"SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                +"WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME LIKE 'fk_prp_mcp_%'")).isEqualTo(5);
            assertThat(fingerprints(clone)).containsExactlyInAnyOrderEntriesOf(original);
            assertThat(fingerprints(source)).containsExactlyInAnyOrderEntriesOf(original);
            assertV24(source);
            assertThat(count(clone,"SELECT COUNT(*) FROM prp_tasks WHERE user_id=12001"))
                .isEqualTo(24);
            assertThat(count(clone,"SELECT COUNT(*) FROM prp_tasks WHERE user_id=12002"))
                .isEqualTo(3);
        }
        System.out.println("CI_FULL_SYNTHETIC_V24_RESTORED_CLONE_V28_OWNER_TASK_FINANCE_VIDEO_VOCAL_PRESERVED=YES");
        System.out.println("CI_SOURCE_DB_STAYED_V24=YES");
    }

    @Test
    void guardedFullV24BackupRestorePhasedContract() throws Exception {
        guard();
        if ("seed".equals(System.getenv("PRP_CI_FULL_SCHEMA_PHASE"))) seed();
        else verifyClone();
        System.out.println("NO_PRODUCTION_DATABASE_OR_OWNER_DATA_ACCESSED=YES");
    }
}
