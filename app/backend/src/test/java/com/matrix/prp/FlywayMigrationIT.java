package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/** Runs on two isolated real MySQL schemas provisioned by CI; never targets production. */
@EnabledIfEnvironmentVariable(named = "MATRIX_PRP_FLYWAY_FRESH_URL", matches = "jdbc:mysql:.+")
class FlywayMigrationIT {
    private String user() { return System.getenv("MATRIX_PRP_FLYWAY_DB_USER"); }
    private String password() { return System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"); }

    private Flyway flyway(String url) {
        return Flyway.configure().dataSource(url, user(), password())
                .locations("classpath:db/migration")
                .baselineVersion("7")
                .baselineOnMigrate(false)
                .cleanDisabled(true)
                .load();
    }

    private long count(String url, String sql) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, user(), password());
                PreparedStatement statement = connection.prepareStatement(sql);
                ResultSet result = statement.executeQuery()) {
            result.next();
            return result.getLong(1);
        }
    }

    private void insertSentinel(String url, String username) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, user(), password())) {
            try (PreparedStatement userInsert = connection.prepareStatement(
                    "INSERT INTO prp_users(username,display_name,password_hash) VALUES(?,?,?)")) {
                userInsert.setString(1, username);
                userInsert.setString(2, "Migration CI");
                userInsert.setString(3, "not-a-login");
                userInsert.executeUpdate();
            }
            try (PreparedStatement taskInsert = connection.prepareStatement(
                    "INSERT INTO prp_tasks(user_id,module_code,title,description,created_at,updated_at) " +
                            "SELECT id,'work','MIGRATION_SENTINEL','preserve row',NOW(6),NOW(6) " +
                            "FROM prp_users WHERE username=?")) {
                taskInsert.setString(1, username);
                assertThat(taskInsert.executeUpdate()).isEqualTo(1);
            }
        }
    }

    @Test
    void newSchemaMigratesTwiceWithoutChangingExistingRows() throws SQLException {
        String url = System.getenv("MATRIX_PRP_FLYWAY_FRESH_URL");
        Flyway migration = flyway(url);
        assertThat(migration.migrate().migrationsExecuted).isEqualTo(7);
        assertThat(migration.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1")).isEqualTo(7);

        insertSentinel(url, "flyway_fresh_ci");
        long before = count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'");
        assertThat(migration.migrate().migrationsExecuted).isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'")).isEqualTo(before);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods WHERE owner_user_id IS NULL"))
                .isGreaterThanOrEqualTo(9);
    }

    @Test
    void explicitLegacyBaselinePreservesPreexistingRows() throws SQLException {
        String url = System.getenv("MATRIX_PRP_FLYWAY_LEGACY_URL");
        insertSentinel(url, "flyway_legacy_ci");
        long before = count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'");
        long seedRows = count(url, "SELECT COUNT(*) FROM prp_wellness_foods");
        Flyway migration = flyway(url);
        assertThat(migration.baseline().successfullyBaselined).isTrue();
        assertThat(migration.validateWithResult().validationSuccessful).isTrue();
        assertThat(migration.migrate().migrationsExecuted).isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'")).isEqualTo(before);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods")).isEqualTo(seedRows);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1")).isEqualTo(1);
    }
}
