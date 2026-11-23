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

/**
 * Disposable GitHub-runner-only synthetic backup/clone/restore for Health V30.
 * Source: fake V7-baselined V29 MySQL with two synthetic owners and wellness rows.
 * Clone:  mysqldump restore, additive V30, then restore the original V29 dump.
 * This is NOT actual production backup/restore acceptance or release approval.
 */
class IsolatedV29BackupRestoreWellnessV30IT {
    private static final String DATABASE = "prp_health_v30_recovery_ci";
    private static final String SOURCE_URL =
        "jdbc:mysql://127.0.0.1:13312/" + DATABASE
            + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String CLONE_URL =
        "jdbc:mysql://127.0.0.1:13313/" + DATABASE
            + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String USER = "prp_ci";
    private static final Map<String, String> SNAPSHOTS = Map.of(
        "owners", "SELECT id,username,display_name,enabled FROM prp_users ORDER BY id",
        "tasks", "SELECT id,user_id,module_code,title,status,deleted FROM prp_tasks ORDER BY id",
        "finance", "SELECT id,user_id,type,amount,category,deleted FROM prp_finance_transactions ORDER BY id",
        "meals", "SELECT id,user_id,meal_date,meal_type,note,idempotency_key FROM prp_wellness_meals ORDER BY id",
        "items", "SELECT id,meal_id,food_id,food_name,grams,calories,protein_g,carbs_g,fat_g,is_estimate FROM prp_wellness_meal_items ORDER BY id",
        "exercises", "SELECT id,user_id,performed_on,name,duration_minutes,estimated_kcal FROM prp_wellness_exercises ORDER BY id",
        "metrics", "SELECT id,user_id,measured_on,weight_kg,body_fat_pct FROM prp_wellness_body_metrics ORDER BY id",
        "history", "SELECT installed_rank,version,type,script,checksum,success FROM flyway_schema_history WHERE installed_rank<=23 ORDER BY installed_rank"
    );

    private static String phase() {
        String value = System.getenv("PRP_CI_HEALTH_V30_PHASE");
        if (!"seed".equals(value) && !"verify_clone".equals(value)
                && !"verify_fallback".equals(value)) {
            throw new SecurityException("INVALID_DISPOSABLE_V30_PHASE");
        }
        return value;
    }

    private static void guard() {
        String password = System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD");
        String run = System.getenv("GITHUB_RUN_ID");
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"YES".equals(System.getenv("PRP_CI_HEALTH_V30_RESTORE_ONLY"))
                || !SOURCE_URL.equals(System.getenv("PRP_CI_HEALTH_V30_SOURCE_URL"))
                || !CLONE_URL.equals(System.getenv("PRP_CI_HEALTH_V30_CLONE_URL"))
                || !USER.equals(System.getenv("MATRIX_PRP_FLYWAY_DB_USER"))
                || password == null || password.length() < 32
                || run == null || !run.matches("[0-9]+")) {
            throw new SecurityException("DISPOSABLE_SYNTHETIC_V30_ONLY");
        }
        phase();
    }

    private static Connection connect(String url) throws Exception {
        if (!SOURCE_URL.equals(url) && !CLONE_URL.equals(url)) {
            throw new SecurityException("UNAPPROVED_DATABASE_URL");
        }
        return DriverManager.getConnection(url, USER,
            System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"));
    }

    private static Flyway flyway(String url, String version) {
        if (!SOURCE_URL.equals(url) && !CLONE_URL.equals(url)) {
            throw new SecurityException("UNAPPROVED_FLYWAY_URL");
        }
        return Flyway.configure()
            .dataSource(url, USER, System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"))
            .locations("classpath:db/migration")
            .baselineVersion("7")
            .baselineOnMigrate(false)
            .cleanDisabled(true)
            .validateOnMigrate(true)
            .target(MigrationVersion.fromVersion(version))
            .load();
    }

    private static long count(String url, String sql) throws Exception {
        try (Connection c = connect(url);
             Statement s = c.createStatement();
             ResultSet r = s.executeQuery(sql)) {
            assertThat(r.next()).isTrue();
            return r.getLong(1);
        }
    }

    private static void write(String url, String sql, Object... args) throws Exception {
        try (Connection c = connect(url);
             PreparedStatement s = c.prepareStatement(sql)) {
            for (int i = 0; i < args.length; i++) {
                s.setObject(i + 1, args[i]);
            }
            assertThat(s.executeUpdate()).isEqualTo(1);
        }
    }

    private static String hash(String url, String sql) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (Connection c = connect(url);
             PreparedStatement s = c.prepareStatement(sql);
             ResultSet r = s.executeQuery()) {
            while (r.next()) {
                for (int i = 1; i <= r.getMetaData().getColumnCount(); i++) {
                    String value = r.getString(i);
                    digest.update((value == null ? "<NULL>" : value)
                        .getBytes(StandardCharsets.UTF_8));
                    digest.update((byte) 0x1f);
                }
                digest.update((byte) 0x0a);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static Map<String, String> fingerprints(String url) throws Exception {
        Map<String, String> result = new LinkedHashMap<>();
        for (var entry : SNAPSHOTS.entrySet()) {
            result.put(entry.getKey(), hash(url, entry.getValue()));
        }
        return result;
    }

    private static long tables(String url) throws Exception {
        return count(url, "SELECT COUNT(*) FROM information_schema.TABLES "
            + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'");
    }

    private static void assertV29(String url) throws Exception {
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history")).isEqualTo(23);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
            + "WHERE installed_rank=1 AND version='7' AND type='BASELINE' "
            + "AND checksum IS NULL AND success=1")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
            + "WHERE type='SQL' AND success=1 "
            + "AND CAST(version AS UNSIGNED) BETWEEN 8 AND 29")).isEqualTo(22);
        for (String table : new String[] {
            "prp_wellness_meal_analyses", "prp_wellness_meal_item_nutrients"}) {
            assertThat(count(url, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='" + table + "'"))
                .isZero();
        }
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_meals")).isEqualTo(2);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_meal_items")).isEqualTo(2);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_exercises")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_body_metrics")).isEqualTo(1);
    }

    private static void seed() throws Exception {
        assertThat(tables(SOURCE_URL)).isZero();
        assertThat(tables(CLONE_URL)).isZero();
        assertThat(flyway(SOURCE_URL, "7").migrate().migrationsExecuted).isEqualTo(7);
        // Recreate the production-shaped V7 manual Flyway baseline ONLY on
        // this empty, explicitly CI-owned source database.
        try (Connection c = connect(SOURCE_URL); Statement s = c.createStatement()) {
            s.execute("DROP TABLE flyway_schema_history");
        }
        assertThat(flyway(SOURCE_URL, "29").baseline().successfullyBaselined).isTrue();
        assertThat(flyway(SOURCE_URL, "29").migrate().migrationsExecuted).isEqualTo(22);
        new FlywayV28ToV29IT().populateSyntheticV28(SOURCE_URL);
        for (long owner : new long[] {928001L, 928002L}) {
            write(SOURCE_URL, "INSERT INTO prp_wellness_meals "
                + "(id,user_id,meal_date,meal_type,note,idempotency_key) "
                + "VALUES(?,?,'2026-11-20','LUNCH','synthetic only',?)",
                owner + 1000, owner, "ci-health-v30-" + owner);
            write(SOURCE_URL, "INSERT INTO prp_wellness_meal_items "
                + "(id,meal_id,food_id,food_name,grams,calories,protein_g,carbs_g,fat_g,is_estimate) "
                + "VALUES(?,?,NULL,'Synthetic meal',100,120,8,22,2,1)",
                owner + 2000, owner + 1000);
        }
        write(SOURCE_URL, "INSERT INTO prp_wellness_exercises "
            + "(user_id,performed_on,name,duration_minutes,estimated_kcal) "
            + "VALUES(928001,'2026-11-20','Synthetic walk',30,100)");
        write(SOURCE_URL, "INSERT INTO prp_wellness_body_metrics "
            + "(user_id,measured_on,weight_kg,body_fat_pct) "
            + "VALUES(928002,'2026-11-20',70.5,20)");
        assertV29(SOURCE_URL);
        assertThat(fingerprints(SOURCE_URL)).hasSize(SNAPSHOTS.size());
        System.out.println("CI_SYNTHETIC_V7_BASELINE_V29_HEALTH_SOURCE_SEEDED=YES");
    }

    private static void verifyClone() throws Exception {
        assertV29(SOURCE_URL);
        assertV29(CLONE_URL);
        Map<String, String> before = fingerprints(SOURCE_URL);
        assertThat(fingerprints(CLONE_URL)).containsExactlyInAnyOrderEntriesOf(before);
        long originalTables = tables(SOURCE_URL);
        assertThat(tables(CLONE_URL)).isEqualTo(originalTables);
        var upgraded = flyway(CLONE_URL, "30");
        assertThat(upgraded.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(upgraded.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history"))
            .isEqualTo(24);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
            + "WHERE installed_rank=24 AND version='30' "
            + "AND script='V30__wellness_analysis_details.sql' "
            + "AND success=1")).isEqualTo(1);
        assertThat(tables(CLONE_URL)).isEqualTo(originalTables + 2);
        assertThat(tables(SOURCE_URL)).isEqualTo(originalTables);
        for (String table : new String[] {
            "prp_wellness_meal_analyses", "prp_wellness_meal_item_nutrients"}) {
            assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM " + table)).isZero();
        }
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
            + "WHERE CONSTRAINT_SCHEMA=DATABASE() "
            + "AND CONSTRAINT_NAME IN ('fk_wellness_analysis_meal',"
            + "'fk_wellness_nutrients_item')")).isEqualTo(2);
        assertThrows(SQLException.class, () -> write(CLONE_URL,
            "INSERT INTO prp_wellness_meal_analyses "
                + "(meal_id,version_number,source_type,raw_extraction_json,analysis_json) "
                + "VALUES(9999999,1,'synthetic','{}','{}')"));
        assertThrows(SQLException.class, () -> write(CLONE_URL,
            "INSERT INTO prp_wellness_meal_item_nutrients "
                + "(meal_item_id,source_type,confidence_level) "
                + "VALUES(9999999,'synthetic','low')"));
        assertThat(fingerprints(CLONE_URL)).containsExactlyInAnyOrderEntriesOf(before);
        assertThat(fingerprints(SOURCE_URL)).containsExactlyInAnyOrderEntriesOf(before);
        assertV29(SOURCE_URL);
        assertThat(upgraded.migrate().migrationsExecuted).isZero();
        System.out.println("CI_SYNTHETIC_RESTORED_V29_CLONE_V30_HEALTH_INTACT=PASS");
        System.out.println("CI_HEALTH_V30_NEW_TABLES_EMPTY_AND_FK_ENFORCED=PASS");
        System.out.println("CI_SYNTHETIC_SOURCE_V29_UNMODIFIED=YES");
    }

    private static void verifyFallback() throws Exception {
        assertV29(SOURCE_URL);
        assertV29(CLONE_URL);
        assertThat(fingerprints(CLONE_URL))
            .containsExactlyInAnyOrderEntriesOf(fingerprints(SOURCE_URL));
        assertThat(tables(CLONE_URL)).isEqualTo(tables(SOURCE_URL));
        assertThat(flyway(CLONE_URL, "29").validateWithResult().validationSuccessful)
            .isTrue();
        System.out.println("CI_SYNTHETIC_V30_FALLBACK_RESTORED_V29=PASS");
        System.out.println("NO_REAL_PRODUCTION_DATA_OR_BACKUPS_USED=YES");
        System.out.println("PRODUCTION_RELEASE_AUTHORIZED=NO");
    }

    @Test
    void guardedHealthV30SyntheticRestoreAndFallback() throws Exception {
        guard();
        switch (phase()) {
            case "seed" -> seed();
            case "verify_clone" -> verifyClone();
            case "verify_fallback" -> verifyFallback();
            default -> throw new SecurityException("UNREVIEWED_CI_PHASE");
        }
    }
}
