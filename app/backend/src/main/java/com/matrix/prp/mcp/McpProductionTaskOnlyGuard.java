package com.matrix.prp.mcp;

import java.net.URI;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * Optional fail-closed lock for the initial *production* PRP owner-task MCP
 * canary, where owner/task rows must come from the existing PRP database.
 *
 * This is a configuration safety interlock, not production deployment approval,
 * a database backup, an OAuth client registration or proof of user consent.
 * It cannot be enabled by a model or by a request parameter.
 */
@Component
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "production-tasks-only", havingValue = "true")
public final class McpProductionTaskOnlyGuard {
    public McpProductionTaskOnlyGuard(
        Environment environment,
        @Value("${matrix-prp.mcp.enabled:false}") boolean mcpEnabled,
        @Value("${matrix-prp.mcp.oauth.enabled:false}") boolean oauthEnabled,
        @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled,
        @Value("${matrix-prp.mcp.oauth.advertised-scopes:prp.tasks.read}") String scopes,
        @Value("${spring.datasource.url:}") String jdbcUrl,
        @Value("${spring.flyway.enabled:false}") boolean flywayEnabled) {
        verify(mcpEnabled, oauthEnabled, writeEnabled, scopes, jdbcUrl,
            flywayEnabled, List.of(environment.getActiveProfiles()));
    }

    static void verify(boolean mcp, boolean oauth, boolean write, String scopes,
                       String jdbcUrl, boolean flyway, List<String profiles) {
        if (!mcp || !oauth || write || flyway
                || profiles.contains("test") || profiles.contains("video-integration")) {
            throw new IllegalStateException("Production MCP task-read canary configuration rejected");
        }

        // Exactly one advertised scope; no finance, wellness, draft or write
        // capabilities. A comma/whitespace/duplicate must not be normalized
        // into broader permissions or hidden at the discovery endpoint.
        if (!"prp.tasks.read".equals(scopes)) {
            throw new IllegalStateException("Production MCP task-read scope must be exact");
        }

        // The currently reviewed production PRP connects through loopback to
        // the actual matrix_prp database. Fail closed on isolated V2 schema,
        // remote database, alternate URI syntax, or any embedded credentials.
        // This comparison is a startup assertion only: it does not open JDBC
        // or establish that the server has the correct owner/account data.
        try {
            if (jdbcUrl == null || !jdbcUrl.startsWith("jdbc:mysql://")) {
                throw new IllegalArgumentException();
            }
            URI parsed = URI.create(jdbcUrl.substring(5));
            String host = parsed.getHost();
            if (!"mysql".equals(parsed.getScheme()) ||
                    host == null ||
                    !("127.0.0.1".equals(host) || "localhost".equalsIgnoreCase(host)
                        || "[::1]".equals(host)) ||
                    parsed.getRawUserInfo() != null ||
                    parsed.getRawFragment() != null ||
                    !"/matrix_prp".equals(parsed.getRawPath()) ||
                    (parsed.getPort() != -1 && (parsed.getPort() < 1 || parsed.getPort() > 65535))) {
                throw new IllegalArgumentException();
            }
        } catch (RuntimeException invalid) {
            // Avoid printing JDBC URLs, hosts, tokens or other config secrets.
            throw new IllegalStateException("Production MCP task-read database boundary rejected");
        }
    }
}
