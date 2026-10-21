package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import java.util.Arrays;
import java.util.Set;
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
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;

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
        NimbusJwtDecoder decoder = jwksDecoder(jwks);
        decoder.setJwtValidator(jwtValidator(issuer, resource));
        return decoder;
    }

    static NimbusJwtDecoder jwksDecoder(String uri) {
        // Bound an unavailable issuer/JWKS; preserve signature validation and
        // Nimbus key caching. No fallback to a PRP session or an unverified JWT.
        var http = new RestTemplateBuilder().connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3)).build();
        return NimbusJwtDecoder.withJwkSetUri(uri).restOperations(http).build();
    }

    /**
     * Validator shared by the production JWK-backed decoder and cryptographic
     * tests: issuer, token timestamps and exact MCP resource audience.
     */
    static OAuth2TokenValidator<Jwt> jwtValidator(String issuer, String resource) {
        OAuth2TokenValidator<Jwt> issuerAndLifetime = JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audience = jwt -> jwt.getAudience().contains(resource)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token", "Wrong MCP token audience", null));
        return jwt -> {
            var validated = issuerAndLifetime.validate(jwt);
            return validated.hasErrors() ? validated : audience.validate(jwt);
        };
    }

    @Bean
    @Order(1)
    SecurityFilterChain mcpOAuthFilterChain(HttpSecurity http, JwtDecoder mcpJwtDecoder, UserStore users,
                                              McpClientGrantService grants, McpIdentityLinkService links)
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
                    if (token.getIssuer() == null || token.getSubject() == null
                        || token.getSubject().isBlank()) {
                        throw new BadCredentialsException("OAuth issuer/subject is required");
                    }
                    var linked = links.resolveUserId(token.getIssuer().toString(), token.getSubject());
                    if (linked.isEmpty()) {
                        throw new BadCredentialsException("OAuth identity is not linked to PRP");
                    }
                    UserAccount account = users.findById(linked.getAsLong()).orElse(null);
                    if (account == null || !account.enabled()) {
                        throw new BadCredentialsException("PRP account not available");
                    }
                    String clientId = McpOAuthClientIdentity.clientId(token);
                    Set<String> granted = grants.grantedScopes(account.id(), clientId);
                    if (granted.isEmpty()) throw new BadCredentialsException("MCP client not authorized by PRP owner");
                    List<String> scopes = token.getClaimAsStringList("scp");
                    if (scopes == null) {
                        String rawScope = token.getClaimAsString("scope");
                        scopes = rawScope == null ? List.of()
                            : Arrays.stream(rawScope.split("\\s+")).filter(v -> !v.isBlank()).toList();
                    }
                    var authorities = scopes.stream().filter(granted::contains)
                        .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
                        .collect(Collectors.toList());
                    return new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                        account.profile(), token, authorities);
                })))
            .addFilterAfter(new McpVerifiedPrincipalCaptureFilter(), BearerTokenAuthenticationFilter.class)
            .build();
    }
}
