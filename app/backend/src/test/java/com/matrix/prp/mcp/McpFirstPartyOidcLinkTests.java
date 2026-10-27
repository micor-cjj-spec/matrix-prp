package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class McpFirstPartyOidcLinkTests {
    private static final String ISSUER = "https://auth-test.micor.top/realms/prp-mcp";
    private static final String RESOURCE = "https://prp-test.micor.top/api/mcp";
    private static final String CALLBACK = "https://prp-test.micor.top/prp/me/mcp-link/callback";
    private static final String FIRST_PARTY = "prp-first-party-link";
    private static final String CHATGPT = "https://chatgpt.com/oauth/client.json";

    private final JdbcTemplate db = mock(JdbcTemplate.class);
    private final UserStore users = mock(UserStore.class);
    private final PasswordEncoder passwords = mock(PasswordEncoder.class);
    private final LoginAttemptLimiter limiter = mock(LoginAttemptLimiter.class);
    private final McpClientGrantService grants = mock(McpClientGrantService.class);
    private final McpIdentityLinkService identities = mock(McpIdentityLinkService.class);
    private final RestTemplateBuilder builder = mock(RestTemplateBuilder.class);
    private final RestTemplate outbound = mock(RestTemplate.class);
    private McpFirstPartyOidcLinkService service;

    private McpFirstPartyOidcLinkService service(
            boolean oauth, String issuer, String jwks, String resource,
            String client, String callback) {
        return new McpFirstPartyOidcLinkService(
            db, users, passwords, limiter, grants, identities, builder,
            oauth, issuer, jwks, resource, client, callback);
    }

    @BeforeEach
    void init() {
        when(builder.connectTimeout(any())).thenReturn(builder);
        when(builder.readTimeout(any())).thenReturn(builder);
        when(builder.build()).thenReturn(outbound);
        service = service(true, ISSUER, ISSUER + "/protocol/openid-connect/certs",
                          RESOURCE, FIRST_PARTY, CALLBACK);
        // Constructor configures the mock's no-redirect HTTPS request factory.
        // Negative tests must count only actual network methods afterwards.
        clearInvocations(outbound);
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(7, "owner", "Owner"), null, java.util.List.of()));
    }

    @AfterEach
    void clear() {
        SecurityContextHolder.clearContext();
    }

    private void authorizedOwner() {
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of("prp.tasks.read"));
        when(users.findById(7L))
            .thenReturn(Optional.of(new UserAccount(7, "owner", "Owner", "encoded", false, true)));
        when(passwords.matches("correct-password", "encoded")).thenReturn(true);
        when(db.queryForObject(anyString(), eq(Integer.class), eq(7L))).thenReturn(0);
    }

    @Test
    void mustBeSeparateFromChatgptAndUseExactHttpsCallbackAndIssuerJwks() {
        assertThatThrownBy(() -> service(false, ISSUER,
            ISSUER + "/protocol/openid-connect/certs", RESOURCE, FIRST_PARTY, CALLBACK))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> service(true, ISSUER,
            "https://evil.example.org/keys", RESOURCE, FIRST_PARTY, CALLBACK))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> service(true, ISSUER,
            ISSUER + "/protocol/openid-connect/certs", RESOURCE, CHATGPT, CALLBACK))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> service(true, ISSUER,
            ISSUER + "/protocol/openid-connect/certs", RESOURCE, FIRST_PARTY,
            "https://example.invalid/prp/me/mcp-link/callback"))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> service(true, ISSUER,
            ISSUER + "/protocol/openid-connect/certs", RESOURCE, FIRST_PARTY,
            CALLBACK + "?next=https://evil.example"))
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void beginRequiresExplicitChatgptConsentAndCorrectPrpPassword() {
        assertThatThrownBy(() -> service.begin("correct-password"))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of("prp.tasks.read"));
        when(users.findById(7L))
            .thenReturn(Optional.of(new UserAccount(7, "owner", "Owner", "encoded", false, true)));
        assertThatThrownBy(() -> service.begin("wrong-password"))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }

    @Test
    void beginCreatesOnePrivatePkceStateAndOnlyOpenidIssuerAuthorization() {
        authorizedOwner();
        String authorizationUrl = service.begin("correct-password").authorizeUrl();
        assertThat(authorizationUrl).startsWith(
            ISSUER + "/protocol/openid-connect/auth?");
        assertThat(authorizationUrl).contains("response_type=code")
            .contains("client_id=" + FIRST_PARTY)
            .contains("scope=openid")
            .contains("code_challenge_method=S256")
            .contains("state=")
            .contains("nonce=")
            .doesNotContain("access_token")
            .doesNotContain("prp.finance")
            .doesNotContain("prp.write")
            .doesNotContain("correct-password");
        verify(db, times(1)).update(startsWith(
            "INSERT INTO prp_mcp_oidc_link_flows"), any(Object[].class));
    }

    @Test
    void malformedOrUntrustedCallbackIsRejectedBeforeTokenExchange() {
        assertThatThrownBy(() -> service.finish("bad", "code", ISSUER))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> service.finish("A".repeat(43), "code",
                "https://attacker.invalid/realms/prp-mcp"))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> service.finish("A".repeat(43), "code", ISSUER))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(outbound);
        verifyNoInteractions(identities);
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void consumedStateStaysConsumedEvenIfTokenEndpointFails() throws Exception {
        // Simulate a previously issued, authenticated PRP-owned state.
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of("prp.tasks.read"));
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenAnswer(call -> {
            org.springframework.jdbc.core.RowMapper mapper = call.getArgument(1);
            java.sql.ResultSet rs = mock(java.sql.ResultSet.class);
            when(rs.getLong(1)).thenReturn(7L);
            when(rs.getString(2)).thenReturn("C".repeat(64));
            when(rs.getString(3)).thenReturn("N".repeat(43));
            return java.util.List.of(mapper.mapRow(rs, 0));
        });
        when(db.update(startsWith("UPDATE prp_mcp_oidc_link_flows"),
                       any(Object[].class))).thenReturn(1, 0);
        when(outbound.postForObject(anyString(), any(), eq(java.util.Map.class)))
            .thenThrow(new org.springframework.web.client.ResourceAccessException("synthetic-failure"));
        String state = "S".repeat(43);
        assertThatThrownBy(() -> service.finish(state, "synthetic-code", ISSUER))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("First-party Keycloak identity verification failed");
        verify(outbound, times(1)).postForObject(anyString(), any(), eq(java.util.Map.class));
        // A second request for the same state must not call Keycloak again.
        assertThatThrownBy(() -> service.finish(state, "synthetic-code", ISSUER))
            .isInstanceOf(ResponseStatusException.class);
        verify(outbound, times(1)).postForObject(anyString(), any(), eq(java.util.Map.class));
        verifyNoInteractions(identities);
    }

    @Test
    void linkCannotProceedAfterClientAuthorizationRevokedBeforeExchange() throws Exception {
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenAnswer(call -> {
            org.springframework.jdbc.core.RowMapper<?> mapper = call.getArgument(1);
            java.sql.ResultSet rs = mock(java.sql.ResultSet.class);
            when(rs.getLong(1)).thenReturn(7L);
            when(rs.getString(2)).thenReturn("C".repeat(64));
            when(rs.getString(3)).thenReturn("N".repeat(43));
            return java.util.List.of(mapper.mapRow(rs, 0));
        });
        when(db.update(startsWith("UPDATE prp_mcp_oidc_link_flows"),
                       any(Object[].class))).thenReturn(1);
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of());
        assertThatThrownBy(() -> service.finish("S".repeat(43), "code", ISSUER))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(outbound, identities);
    }

    @Test
    void noFirstPartySessionCannotReadOrCreatePendingLinkState() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.begin("correct-password"))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> service.finish("A".repeat(43), "code", ISSUER))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db, outbound, identities);
    }
}
