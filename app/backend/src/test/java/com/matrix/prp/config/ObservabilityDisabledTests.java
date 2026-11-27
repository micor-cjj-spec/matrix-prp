package com.matrix.prp.config;

import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ObservabilityDisabledTests {
    @Autowired ApplicationContext context;
    @Autowired Environment env;
    @LocalServerPort int applicationPort;

    private int get(String path) throws Exception {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + applicationPort + path))
                .timeout(java.time.Duration.ofSeconds(10)).GET().build();
        return HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.discarding()).statusCode();
    }

    @Test
    void profileAbsentDisablesExportAndManagementListener() throws Exception {
        assertThat(env.getProperty("management.server.port", Integer.class)).isEqualTo(-1);
        assertThat(env.getProperty("local.management.port", Integer.class)).isNull();
        assertThat(context.getBeansOfType(PrometheusMeterRegistry.class)).isEmpty();
        assertThat(context.getBeansOfType(ObservabilityConfig.class)).isEmpty();
        assertThat(get("/api/health")).isEqualTo(200);
        for (String path : new String[]{"/actuator/prometheus", "/actuator/health", "/actuator/env"}) {
            assertThat(get(path)).isBetween(400, 499);
        }
    }
}
