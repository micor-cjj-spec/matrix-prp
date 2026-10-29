package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/** Isolated CI MySQL only; never use a running PRP database. */
@EnabledIfEnvironmentVariable(named = "MATRIX_PRP_FLYWAY_V28_V29_URL", matches = "jdbc:mysql:.+")
class FlywayV28ToV29IT {
    private long count(String url, String query) throws Exception {
        try (Connection c = DriverManager.getConnection(url,
                System.getenv("MATRIX_PRP_FLYWAY_DB_USER"),
                System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"));
             Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(query)) {
            rs.next();
            return rs.getLong(1);
        }
    }

    private Flyway flyway(String url, String target) {
        var config = Flyway.configure()
                .dataSource(url, System.getenv("MATRIX_PRP_FLYWAY_DB_USER"),
                        System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"))
                .locations("classpath:db/migration")
                .cleanDisabled(true);
        if (target != null) config.target(MigrationVersion.fromVersion(target));
        return config.load();
    }

    @Test
    void upgradesExistingV28WithoutReplacingItsHistory() throws Exception {
        String url = System.getenv("MATRIX_PRP_FLYWAY_V28_V29_URL");
        // Hard-stop before Flyway can connect to any staging or production schema.
        assertThat(url).as("CI-only loopback database")
                .startsWith("jdbc:mysql://127.0.0.1:3306/prp_flyway_v28_v29?");
        assertThat(System.getenv("GITHUB_ACTIONS")).as("GitHub ephemeral runner only")
                .isEqualTo("true");
        Flyway old = flyway(url, "28");
        assertThat(old.migrate().success).isTrue();
        assertThat(old.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='28' AND script='V28__mcp_temporary_client_grant_expiry.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_name='prp_mcp_pairing_grant_leases'"))
                .isEqualTo(1);
        long before = count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1");

        Flyway next = flyway(url, null);
        assertThat(next.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(next.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1"))
                .isEqualTo(before + 1);
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history "
                + "WHERE version='29' AND script='V29__mcp_first_party_oidc_link_flows.sql' "
                + "AND success=1")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables "
                + "WHERE table_schema=DATABASE() AND table_name IN "
                + "('prp_mcp_pairing_grant_leases','prp_mcp_oidc_link_flows')"))
                .isEqualTo(2);
        assertThat(next.migrate().migrationsExecuted).isZero();
    }
}
