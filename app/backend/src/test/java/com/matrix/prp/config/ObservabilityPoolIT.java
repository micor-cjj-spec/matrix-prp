package com.matrix.prp.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

/** Explicit CI-only test against disposable MySQL; never selected by default Surefire. */
class ObservabilityPoolIT {
    @Test
    void actualHikariConnectionLifecycleIsVisibleAsAggregateMetrics() throws Exception {
        assertThat(System.getenv("GITHUB_ACTIONS")).isEqualTo("true");
        assertThat(System.getenv("RUNNER_ENVIRONMENT")).isEqualTo("github-hosted");
        var hikari = new HikariConfig();
        hikari.setJdbcUrl("jdbc:mysql://127.0.0.1:3306/prp_p2_fixture?useSSL=false&allowPublicKeyRetrieval=true");
        hikari.setUsername("p2_fixture");
        hikari.setPassword("ci-only-pool-password");
        hikari.setPoolName("p2_fixture_pool");
        hikari.setMinimumIdle(1);
        hikari.setMaximumPoolSize(2);
        hikari.setConnectionTimeout(5000);
        var config = new ObservabilityConfig();
        try (var registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            registry.config().meterFilter(config.observabilityMetricAllowlist())
                    .meterFilter(config.observabilityPoolBound());
            hikari.setMetricsTrackerFactory(new MicrometerMetricsTrackerFactory(registry));
            try (var pool = new HikariDataSource(hikari)) {
                try (var connection = pool.getConnection()) {
                    assertThat(connection.isValid(2)).isTrue();
                    assertThat(registry.get("hikaricp.connections.active").tag("pool", "p2_fixture_pool").gauge().value()).isEqualTo(1);
                    assertThat(registry.get("hikaricp.connections").tag("pool", "p2_fixture_pool").gauge().value()).isBetween(1.0, 2.0);
                }
                // Hikari caches PoolStats gauges for up to one second.
                Thread.sleep(1200);
                assertThat(registry.get("hikaricp.connections.active").tag("pool", "p2_fixture_pool").gauge().value()).isZero();
                assertThat(registry.get("hikaricp.connections.idle").tag("pool", "p2_fixture_pool").gauge().value()).isGreaterThanOrEqualTo(1);
                assertThat(registry.scrape()).contains("hikaricp_connections_active", "hikaricp_connections_pending")
                        .doesNotContain("ci-only-pool-password", "jdbc:mysql:");
            }
        }
    }
}
