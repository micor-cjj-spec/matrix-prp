package com.matrix.prp.config;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.server.port=0")
@ActiveProfiles({"test", "observability"})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ObservabilityMetricsTests {
    private static final String PASSWORD = "synthetic-test-only-metrics-password";
    private static final String HASH = new BCryptPasswordEncoder(12).encode(PASSWORD);
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build();

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry properties) {
        properties.add("matrix-prp.observability.password-hash", () -> HASH);
    }

    @LocalServerPort int applicationPort;
    @LocalManagementPort int managementPort;
    @Autowired PrometheusMeterRegistry registry;

    private HttpResponse<String> request(int port, String path, String method, String password) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(10)).method(method, HttpRequest.BodyPublishers.noBody());
        if (password != null) {
            var basic = Base64.getEncoder().encodeToString(("prp-metrics:" + password).getBytes(StandardCharsets.UTF_8));
            builder.header("Authorization", "Basic " + basic);
        }
        return HTTP.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void authenticatesOnlyExactReadOnlyManagementEndpointAndPreservesBusinessBoundary() throws Exception {
        assertThat(managementPort).isPositive().isNotEqualTo(applicationPort);
        assertThat(request(applicationPort, "/api/health", "GET", null).statusCode()).isEqualTo(200);
        assertThat(request(managementPort, "/actuator/prometheus", "GET", null).statusCode()).isEqualTo(401);
        assertThat(request(managementPort, "/actuator/prometheus", "GET", "wrong").statusCode()).isEqualTo(401);
        assertThat(request(managementPort, "/actuator/prometheus", "GET", PASSWORD).statusCode()).isEqualTo(200);
        for (String path : new String[]{"/actuator", "/actuator/health", "/actuator/env",
                "/actuator/beans", "/actuator/configprops", "/actuator/heapdump",
                "/actuator/metrics", "/api/health", "/api/tasks"}) {
            assertThat(request(managementPort, path, "GET", PASSWORD).statusCode())
                    .as("management path %s", path).isBetween(400, 499);
        }
        assertThat(request(managementPort, "/actuator/prometheus", "POST", PASSWORD).statusCode()).isBetween(400, 499);
        assertThat(request(managementPort, "/actuator/prometheus", "HEAD", PASSWORD).statusCode()).isBetween(400, 499);
        assertThat(request(applicationPort, "/actuator/prometheus", "GET", PASSWORD).statusCode()).isBetween(400, 499);
        assertThat(request(applicationPort, "/api/tasks", "GET", PASSWORD).statusCode()).isEqualTo(401);
        assertThat(request(applicationPort, "/api/health", "GET", null).statusCode()).isEqualTo(200);
    }

    @Test
    void exposesRealJvmProcessAndHttpMetricsWithoutRawRequestData() throws Exception {
        assertThat(request(applicationPort, "/api/health?marker=p2-secret-query", "GET", null).statusCode()).isEqualTo(200);
        for (int i = 0; i < 6; i++) {
            request(applicationPort, "/p2-private-path-" + i, "GET", null);
        }
        registry.counter("prp.private.business", "owner", "p2-secret-owner").increment();
        registry.counter("jvm.synthetic", "owner", "p2-secret-owner").increment();
        var response = request(managementPort, "/actuator/prometheus", "GET", PASSWORD);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("jvm_memory_used_bytes", "jvm_threads_live_threads",
                "process_uptime_seconds", "http_server_requests_seconds_count",
                "http_server_requests_seconds_bucket", "uri=\"/api/health\"")
                .doesNotContain("p2-secret-query", "p2-private-path-", "p2-secret-owner",
                        "prp_private_business", "jvm_synthetic", PASSWORD, HASH);
        assertThat(registry.find("http.server.requests").tag("uri", "/api/health").timers())
                .anyMatch(timer -> timer.count() > 0 && timer.totalTime(java.util.concurrent.TimeUnit.NANOSECONDS) > 0);
    }

    @Test
    void boundsDistinctUriMethodAndPoolLabels() {
        var config = new ObservabilityConfig();
        try (var meters = new SimpleMeterRegistry()) {
            meters.config().meterFilter(config.observabilityMetricAllowlist())
                    .meterFilter(config.observabilityUriBound()).meterFilter(config.observabilityMethodBound())
                    .meterFilter(config.observabilityPoolBound());
            for (int i = 0; i < 300; i++) {
                Timer.builder("http.server.requests").tag("uri", "/fixture/" + i)
                        .tag("method", "GET").register(meters).record(Duration.ofMillis(1));
            }
            for (int i = 0; i < 30; i++) {
                Timer.builder("http.server.requests").tag("uri", "/fixture/0")
                        .tag("method", "METHOD" + i).register(meters).record(Duration.ofMillis(1));
                meters.gauge("hikaricp.connections", java.util.List.of(io.micrometer.core.instrument.Tag.of("pool", "pool" + i)), i);
            }
            assertThat(meters.find("http.server.requests").timers().stream()
                    .map(t -> t.getId().getTag("uri")).distinct().count()).isEqualTo(256);
            assertThat(meters.find("http.server.requests").timers().stream()
                    .map(t -> t.getId().getTag("method")).distinct().count()).isEqualTo(16);
            assertThat(meters.find("hikaricp.connections").gauges()).hasSize(8);
        }
    }
}
