package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HexFormat;
import java.util.Map;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;

/**
 * CI-only synthetic V29 mysqldump -> separate MySQL restore -> V30 clone upgrade.
 * This NEVER accesses a real PRP database, backup, server, or user record.
 * A passing test is NOT a production restored-backup rehearsal or deploy approval.
 */
class IsolatedV29BackupRestoreWellnessV30IT {
    private static final String SOURCE_URL =
            "jdbc:mysql://127.0.0.1:13320/prp_wellness_v29_restore_ci"
                    + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String CLONE_URL =
            "jdbc:mysql://127.0.0.1:13321/prp_wellness_v29_restore_ci"
                    + "?useSSL=false&allowPublicKeyRetrieval=true";
    private static final String USER = "prp_ci";
    private static final long OWNER = 928001L;
    private static final String MEAL_NOTE = "CI_WELLNESS_V29_PRESERVED_MEAL";
    private final FlywayV28ToV29IT helper = new FlywayV28ToV29IT();

    private static String phase() {
        String value = System.getenv("CI_WELLNESS_RESTORE_PHASE");
        if (!"seed".equals(value) && !"verify_clone".equals(value)) {
            throw new SecurityException("UNKNOWN_WELLNESS_RESTORE_PHASE");
        }
        return value;
    }

    private static void guard() {
        if (!"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"YES".equals(System.getenv("CI_WELLNESS_V29_V30_ONLY"))
                || !SOURCE_URL.equals(System.getenv("CI_WELLNESS_SOURCE_URL"))
                || !CLONE_URL.equals(System.getenv("CI_WELLNESS_CLONE_URL"))
                || !USER.equals(System.getenv("MATRIX_PRP_FLYWAY_DB_USER"))
                || System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD") == null
                || System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD").length() < 32
                || System.getenv("GITHUB_RUN_ID") == null
                || !System.getenv("GITHUB_RUN_ID").matches("[0-9]+")
                || System.getenv("GITHUB_RUN_ATTEMPT") == null
                || !System.getenv("GITHUB_RUN_ATTEMPT").matches("[0-9]+")
                || System.getenv("RUNNER_TEMP") == null) {
            throw new SecurityException("DISPOSABLE_V29_WELLNESS_RESTORE_ONLY");
        }
        phase();
    }

    private static Connection connect(String url) throws SQLException {
        if (!SOURCE_URL.equals(url) && !CLONE_URL.equals(url)) {
            throw new SecurityException("UNREVIEWED_DATABASE_URL");
        }
        return DriverManager.getConnection(url, USER,
                System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"));
    }

    private long count(String url, String query) throws Exception {
        try (Connection c = connect(url);
             var s = c.createStatement();
             ResultSet r = s.executeQuery(query)) {
            assertThat(r.next()).isTrue();
            return r.getLong(1);
        }
    }

    private long tableCount(String url) throws Exception {
        return count(url, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'");
    }

    private long enrichmentTableCount(String url) throws Exception {
        return count(url, "SELECT COUNT(*) FROM information_schema.TABLES "
                + "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
                + "('prp_wellness_meal_analyses','prp_wellness_meal_item_nutrients')");
    }

    private String mealFingerprint(String url) throws Exception {
        String sql = "SELECT m.id,m.user_id,m.meal_date,m.meal_type,m.note,"
                + "m.idempotency_key,m.created_at,i.id,i.meal_id,i.food_id,"
                + "i.food_name,i.grams,i.calories,i.protein_g,i.carbs_g,"
                + "i.fat_g,i.is_estimate FROM prp_wellness_meals m "
                + "JOIN prp_wellness_meal_items i ON i.meal_id=m.id "
                + "WHERE m.user_id=928001 AND m.note='CI_WELLNESS_V29_PRESERVED_MEAL' "
                + "ORDER BY m.id,i.id";
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        int rows = 0;
        try (Connection c = connect(url);
             var s = c.createStatement();
             ResultSet rs = s.executeQuery(sql)) {
            int columns = rs.getMetaData().getColumnCount();
            while (rs.next()) {
                rows++;
                for (int i = 1; i <= columns; i++) {
                    String value = rs.getString(i);
                    digest.update((value == null ? "<NULL>" : value)
                            .getBytes(StandardCharsets.UTF_8));
                    digest.update((byte) 0x1f);
                }
                digest.update((byte) 0x0a);
            }
        }
        assertThat(rows).isEqualTo(1);
        return HexFormat.of().formatHex(digest.digest());
    }

    private long oldMealCount(String url) throws Exception {
        return count(url, "SELECT COUNT(*) FROM prp_wellness_meals m "
                + "JOIN prp_wellness_meal_items i ON i.meal_id=m.id "
                + "WHERE m.user_id=928001 AND m.note='CI_WELLNESS_V29_PRESERVED_MEAL' "
                + "AND m.meal_type='SNACK' AND m.meal_date='2026-07-06' "
                + "AND m.idempotency_key='ci-v29-preserved-meal' "
                + "AND i.food_name='Synthetic legacy V29 meal' "
                + "AND i.grams=80 AND i.calories=320 AND i.is_estimate=1 "
                + "AND i.protein_g IS NULL AND i.carbs_g IS NULL AND i.fat_g IS NULL");
    }

    private void seed() throws Exception {
        assertThat(tableCount(SOURCE_URL)).isZero();
        assertThat(tableCount(CLONE_URL)).isZero();
        Flyway source = helper.flyway(SOURCE_URL, "29");
        assertThat(source.migrate().migrationsExecuted).isEqualTo(29);
        assertThat(source.validateWithResult().validationSuccessful).isTrue();
        helper.populateSyntheticV28(SOURCE_URL);
        helper.insert(SOURCE_URL, "INSERT INTO prp_wellness_meals "
                + "(user_id,meal_date,meal_type,note,idempotency_key) "
                + "VALUES(?,'2026-07-06','SNACK',?,'ci-v29-preserved-meal')",
                OWNER, MEAL_NOTE);
        helper.insert(SOURCE_URL, "INSERT INTO prp_wellness_meal_items "
                + "(meal_id,food_id,food_name,grams,calories,protein_g,carbs_g,"
                + "fat_g,is_estimate) SELECT id,NULL,'Synthetic legacy V29 meal',"
                + "80,320,NULL,NULL,NULL,1 FROM prp_wellness_meals WHERE user_id=? "
                + "AND note=?", OWNER, MEAL_NOTE);
        assertThat(oldMealCount(SOURCE_URL)).isEqualTo(1);
        assertThat(enrichmentTableCount(SOURCE_URL)).isZero();
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='29' AND success=1")).isEqualTo(1);
        assertThat(helper.preservedFingerprints(SOURCE_URL)).hasSize(8);
        assertThat(mealFingerprint(SOURCE_URL)).hasSize(64);
        System.out.println("CI_SYNTHETIC_V29_WELLNESS_SOURCE_SEEDED=PASS");
        System.out.println("NO_REAL_DATABASE_OR_USER_DATA_ACCESSED=YES");
    }

    private void verifyClone() throws Exception {
        Flyway source = helper.flyway(SOURCE_URL, "29");
        Flyway restoredV29 = helper.flyway(CLONE_URL, "29");
        assertThat(source.validateWithResult().validationSuccessful).isTrue();
        assertThat(restoredV29.validateWithResult().validationSuccessful).isTrue();
        Map<String, String> original = helper.preservedFingerprints(SOURCE_URL);
        assertThat(helper.preservedFingerprints(CLONE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);
        String originalMeal = mealFingerprint(SOURCE_URL);
        assertThat(mealFingerprint(CLONE_URL)).isEqualTo(originalMeal);
        assertThat(oldMealCount(SOURCE_URL)).isEqualTo(1);
        assertThat(oldMealCount(CLONE_URL)).isEqualTo(1);
        assertThat(enrichmentTableCount(SOURCE_URL)).isZero();
        assertThat(enrichmentTableCount(CLONE_URL)).isZero();
        long before = tableCount(SOURCE_URL);
        assertThat(tableCount(CLONE_URL)).isEqualTo(before);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='29' AND success=1")).isEqualTo(1);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='30'")).isZero();

        Flyway upgraded = helper.flyway(CLONE_URL, "30");
        assertThat(upgraded.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(upgraded.validateWithResult().validationSuccessful).isTrue();
        assertThat(tableCount(CLONE_URL)).isEqualTo(before + 2);
        assertThat(enrichmentTableCount(CLONE_URL)).isEqualTo(2);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM prp_wellness_meal_analyses"))
                .isZero();
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM prp_wellness_meal_item_nutrients"))
                .isZero();
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='30' AND script='V30__wellness_analysis_details.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(CLONE_URL, "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                + "WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME IN "
                + "('fk_wellness_analysis_meal','fk_wellness_nutrients_item')"))
                .isEqualTo(2);
        // New V30 foreign keys are enforced by real MySQL, not mocked.
        assertThrows(SQLException.class, () -> helper.insert(CLONE_URL,
                "INSERT INTO prp_wellness_meal_item_nutrients "
                + "(meal_item_id,source_type,confidence_level) "
                + "VALUES(999999999,'USER_ESTIMATE','UNVERIFIED')"));
        assertThat(mealFingerprint(CLONE_URL)).isEqualTo(originalMeal);
        assertThat(helper.preservedFingerprints(CLONE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);
        assertThat(upgraded.migrate().migrationsExecuted).isZero();

        // Source is untouched: no V30 history, tables, or change to prior rows.
        assertThat(tableCount(SOURCE_URL)).isEqualTo(before);
        assertThat(enrichmentTableCount(SOURCE_URL)).isZero();
        assertThat(count(SOURCE_URL, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='30'")).isZero();
        assertThat(mealFingerprint(SOURCE_URL)).isEqualTo(originalMeal);
        assertThat(helper.preservedFingerprints(SOURCE_URL))
                .containsExactlyInAnyOrderEntriesOf(original);

        System.out.println("CI_SYNTHETIC_V29_DUMP_RESTORE_V30_CLONE=PASS");
        System.out.println("CI_SYNTHETIC_V29_ORIGINAL_SOURCE_UNCHANGED=YES");
        System.out.println("CI_SYNTHETIC_V30_ORPHAN_NUTRIENT_FK_REJECTED=YES");
        System.out.println("NO_PRODUCTION_RESTORED_BACKUP_TESTED=YES");
        System.out.println("PRODUCTION_RELEASE_APPROVED=NO");
    }

    @Test
    void guardedSyntheticV29BackupRestoreAndV30CloneUpgrade() throws Exception {
        guard();
        if ("seed".equals(phase())) {
            seed();
        } else {
            verifyClone();
        }
    }
}
