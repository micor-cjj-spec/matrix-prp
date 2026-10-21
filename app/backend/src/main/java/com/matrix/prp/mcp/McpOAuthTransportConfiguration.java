package com.matrix.prp.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.modelcontextprotocol.json.jackson.JacksonMcpJsonMapper;
import io.modelcontextprotocol.common.McpTransportContext;
import io.modelcontextprotocol.server.transport.WebMvcStatelessServerTransport;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

/**
 * Capture only a Spring-Security-authenticated identity on the HTTP request thread.
 * Never copy model arguments or arbitrary HTTP headers into the trusted identity.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthTransportConfiguration {
    public static final String VERIFIED_AUTH = "prp.mcp.verifiedAuthentication";

    @Bean
    WebMvcStatelessServerTransport oauthMcpTransport(
            @Qualifier("mcpServerObjectMapper") ObjectMapper mapper) {
        return WebMvcStatelessServerTransport.builder()
            .jsonMapper(new JacksonMcpJsonMapper(mapper))
            .messageEndpoint("/api/mcp")
            .contextExtractor(request -> {
                Authentication auth = SecurityContextHolder.getContext().getAuthentication();
                if (auth == null || !auth.isAuthenticated()) return McpTransportContext.EMPTY;
                return McpTransportContext.create(Map.of(VERIFIED_AUTH, auth));
            })
            .build();
    }
}
