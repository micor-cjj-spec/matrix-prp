package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.modelcontextprotocol.json.jackson.JacksonMcpJsonMapper;
import io.modelcontextprotocol.common.McpTransportContext;
import io.modelcontextprotocol.server.transport.WebMvcStatelessServerTransport;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.security.core.Authentication;
import org.springframework.web.servlet.function.EntityResponse;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

/**
 * Capture only a Spring-Security-authenticated identity on the HTTP request thread.
 * Never copy model arguments or arbitrary HTTP headers into the trusted identity.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthTransportConfiguration {
    public static final String VERIFIED_AUTH = "prp.mcp.verifiedAuthentication";
    static final String LEGACY_DISCOVERY_PROBE = "prp.mcp.legacyDiscoveryProbe";

    @Bean
    RouterFunction<ServerResponse> webMvcStatelessServerRouterFunction(
            WebMvcStatelessServerTransport oauthMcpTransport) {
        return oauthMcpTransport.getRouterFunction().filter((request, next) -> {
            ServerResponse response = next.handle(request);
            Object marker = request.servletRequest().getAttribute(LEGACY_DISCOVERY_PROBE);
            if (marker instanceof AtomicBoolean probe && probe.get()
                    && response.statusCode().value() == 200
                    && response instanceof EntityResponse<?> entity) {
                // HTTP dual-era clients detect legacy servers from an unsuccessful
                // modern probe. A JSON-RPC error inside HTTP 200 is insufficient.
                return ServerResponse.badRequest()
                    .headers(headers -> headers.addAll(response.headers()))
                    .cookies(cookies -> cookies.addAll(response.cookies()))
                    .body(entity.entity());
            }
            return response;
        });
    }

    @Bean(destroyMethod = "")
    @Primary
    io.modelcontextprotocol.spec.McpStatelessServerTransport legacyDiscoveryTransport(
            WebMvcStatelessServerTransport oauthMcpTransport) {
        return new McpLegacyDiscoveryTransport(oauthMcpTransport);
    }

    @Bean
    WebMvcStatelessServerTransport oauthMcpTransport(
            @Qualifier("mcpServerObjectMapper") ObjectMapper mapper) {
        return WebMvcStatelessServerTransport.builder()
            .jsonMapper(new JacksonMcpJsonMapper(mapper))
            .messageEndpoint("/api/mcp")
            .contextExtractor(request -> {
                Object verified = request.servletRequest().getAttribute(VERIFIED_AUTH);
                Authentication auth = verified instanceof Authentication saved ? saved : null;
                if (auth == null || !auth.isAuthenticated()) return McpTransportContext.EMPTY;
                var probe = new AtomicBoolean();
                request.servletRequest().setAttribute(LEGACY_DISCOVERY_PROBE, probe);
                return McpTransportContext.create(Map.of(VERIFIED_AUTH, auth, LEGACY_DISCOVERY_PROBE, probe));
            })
            .build();
    }
}
