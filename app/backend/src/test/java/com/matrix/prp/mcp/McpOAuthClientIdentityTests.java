package com.matrix.prp.mcp;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class McpOAuthClientIdentityTests {
    private static Jwt token(String clientId, String azp) {
        var builder = Jwt.withTokenValue("test-token-not-for-production")
            .header("alg", "RS256")
            .subject("oauth-user")
            .issuedAt(Instant.now().minusSeconds(5))
            .expiresAt(Instant.now().plusSeconds(300));
        if (clientId != null) builder.claim("client_id", clientId);
        if (azp != null) builder.claim("azp", azp);
        return builder.build();
    }

    @Test
    void acceptsKeycloakSignedAzpWhenClientIdClaimMissing() {
        assertThat(McpOAuthClientIdentity.clientId(token(null, "keycloak-registered-client")))
            .isEqualTo("keycloak-registered-client");
    }

    @Test
    void acceptsMatchingClientIdAndAzp() {
        assertThat(McpOAuthClientIdentity.clientId(token("known-client", "known-client")))
            .isEqualTo("known-client");
    }

    @Test
    void rejectsConflictingClientClaims() {
        assertThatThrownBy(() -> McpOAuthClientIdentity.clientId(token("trusted-client", "attacker-client")))
            .isInstanceOf(ResponseStatusException.class);
    }

    @Test
    void rejectsMissingOrMalformedClientIdentity() {
        assertThatThrownBy(() -> McpOAuthClientIdentity.clientId(token(null, null)))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> McpOAuthClientIdentity.clientId(token(null, "untrusted client")))
            .isInstanceOf(ResponseStatusException.class);
    }
}
