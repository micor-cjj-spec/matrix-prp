package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import java.net.URI;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;

/**
 * Only the MCP protocol endpoint uses third-party OAuth access tokens.
 * PRP's existing /api/** JWT login stays unchanged, including the separate
 * human-only draft approval page. Enabling OAuth fails closed on configuration
 * errors instead of falling back to a PRP session JWT.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "matrix-prp.mcp.oauth", name = "enabled", havingValue = "true")
public class McpOAuthResourceServerConfig {
    private final String issuer;
    private final String jwks;
    private final String resource;

    public McpOAuthResourceServerConfig(
        @Value("${matrix-prp.mcp.oauth.issuer:}") String issuer,
        @Value("${matrix-prp.mcp.oauth.jwk-set-uri:}") String jwks,
        @Value("${matrix-prp.mcp.oauth.resource:}") String resource) {
        this.issuer = strictHttps(issuer, "MCP OAuth issuer");
        this.jwks = strictHttps(jwks, "MCP OAuth JWKS");
        this.resource = strictHttps(resource, "MCP OAuth resource");
        if (!URI.create(this.resource).getPath().endsWith("/api/mcp")) {
            throw new IllegalStateException("MCP OAuth resource must identify the actual /api/mcp endpoint");
        }
    }

    static String strictHttps(String value, String label) {
        try {
            URI uri = URI.create(value == null ? "" : value);
            if (!"https".equals(uri.getScheme()) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getFragment() != null
                || uri.getQuery() != null || uri.getPort() != -1 && uri.getPort() != 443) {
                throw new IllegalArgumentException();
            }
            return uri.toString();
        } catch (RuntimeException ex) {
            throw new IllegalStateException(label + " must be an explicit HTTPS URL", ex);
        }
    }

    @Bean("mcpJwtDecoder")
    JwtDecoder mcpJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwks).build();
        OAuth2TokenValidator<Jwt> issuerAndLifetime = JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience = jwt -> jwt.getAudience().contains(resource)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Wrong MCP token audience", null));
        decoder.setJwtValidator(jwt -> {
            var issuerResult = issuerAndLifetime.validate(jwt);
            if (issuerResult.hasErrors()) return issuerResult;
            return audience.validate(jwt);
        });
        return decoder;
    }

    @Bean
    @Order(1)
    SecurityFilterChain mcpOAuthFilterChain(HttpSecurity http, JwtDecoder mcpJwtDecoder, UserStore users)
        throws Exception {
        var metadataUri = McpOAuthMetadataController.metadataUrl(resource);
        return http.securityMatcher("/api/mcp")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint((request, response, cause) -> {
                    response.setStatus(HttpStatus.UNAUTHORIZED.value());
                    response.setHeader("WWW-Authenticate",
                        "Bearer resource_metadata=\"" + metadataUri + "\"");
                })
                .jwt(jwt -> jwt.decoder(mcpJwtDecoder).jwtAuthenticationConverter(token -> {
                    Object rawId = token.getClaim("prp_user_id");
                    if (!(rawId instanceof Number number) || number.longValue() <= 0
                        || number.doubleValue() != number.longValue()) {
                        throw new BadCredentialsException("Invalid PRP user binding");
                    }
                    UserAccount account = users.findById(number.longValue()).orElse(null);
                    if (account == null || !account.enabled()) {
                        throw new BadCredentialsException("PRP account not available");
                    }
                    List<String> scopes = token.getClaimAsStringList("scp");
                    if (scopes == null) {
                        String rawScope = token.getClaimAsString("scope");
                        scopes = rawScope == null ? List.of()
                            : Arrays.stream(rawScope.split("\\s+")).filter(v -> !v.isBlank()).toList();
                    }
                    var authorities = scopes.stream().filter(scope -> scope.matches("prp\\.(tasks|finance|wellness|write)\\.(read|create|confirm|status)"))
                        .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
                        .collect(Collectors.toList());
                    return new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                        account.profile(), token, authorities);
                })))
            .build();
    }
}
