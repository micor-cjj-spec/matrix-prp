package com.matrix.prp.mcp;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;

/**
 * A bootstrap-only OAuth chain which validates the bearer without requiring
 * an existing PRP identity link (the link is what this endpoint creates).
 * All other MCP operations require the established subject mapping.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthLinkSecurityConfig {
    @Bean
    @Order(0)
    SecurityFilterChain mcpIdentityLinkChain(HttpSecurity http, JwtDecoder mcpJwtDecoder) throws Exception {
        return http.securityMatcher("/api/mcp/link")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt.decoder(mcpJwtDecoder)))
            .addFilterAfter(new McpVerifiedJwtCaptureFilter(), BearerTokenAuthenticationFilter.class)
            .build();
    }
}
