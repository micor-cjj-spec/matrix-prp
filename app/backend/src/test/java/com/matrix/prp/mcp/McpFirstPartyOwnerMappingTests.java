package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class McpFirstPartyOwnerMappingTests {
    private static final String ISSUER = "https://auth-test.micor.top/realms/prp-mcp";
    private static final String SUBJECT = "verified-keycloak-subject";
    private static final String CHATGPT = "https://chatgpt.com/oauth/client.json";
    private final JdbcTemplate db = mock(JdbcTemplate.class);
    private final UserStore users = mock(UserStore.class);
    private final PasswordEncoder encoder = mock(PasswordEncoder.class);
    private final LoginAttemptLimiter limiter = mock(LoginAttemptLimiter.class);
    private final McpClientGrantService grants = mock(McpClientGrantService.class);
    private final McpIdentityLinkService links = new McpIdentityLinkService(
        db, users, encoder, limiter, grants, ISSUER);

    @BeforeEach
    void ownerApproved() {
        when(users.findById(7L)).thenReturn(Optional.of(
            new UserAccount(7, "owner", "Owner", "hashed", false, true)));
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of("prp.tasks.read"));
    }

    @Test
    void invalidIssuerAndWrongIntendedClientCannotInsert() {
        assertThatThrownBy(() -> links.linkFirstPartyOwner(
            7L, "https://wrong-issuer.example.org", SUBJECT, CHATGPT))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> links.linkFirstPartyOwner(
            7L, ISSUER, SUBJECT, "prp-first-party-link"))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }

    @Test
    void disabledOwnerOrRevokedTaskGrantCannotLink() {
        when(users.findById(7L)).thenReturn(Optional.of(
            new UserAccount(7, "owner", "Owner", "hashed", false, false)));
        assertThatThrownBy(() -> links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT))
            .isInstanceOf(ResponseStatusException.class);
        when(users.findById(7L)).thenReturn(Optional.of(
            new UserAccount(7, "owner", "Owner", "hashed", false, true)));
        when(grants.grantedScopes(7L, CHATGPT)).thenReturn(Set.of());
        assertThatThrownBy(() -> links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }

    @Test
    void verifiedSubjectBoundToAnotherOwnerFailsClosed() {
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenAnswer(invocation -> {
            String sql = invocation.getArgument(0);
            return sql.contains("WHERE issuer=? AND subject=?") ? List.of(99L) : List.of();
        });
        assertThatThrownBy(() -> links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("linked to another PRP account");
        verify(db, never()).update(anyString(), any(Object[].class));
    }

    @Test
    void ownerBoundToAnotherVerifiedSubjectFailsClosed() {
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenAnswer(invocation -> {
            String sql = invocation.getArgument(0);
            return sql.contains("WHERE user_id=? AND issuer=?") ?
                List.of("other-verified-subject") : List.of();
        });
        assertThatThrownBy(() -> links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("already linked to another OIDC identity");
        verify(db, never()).update(anyString(), any(Object[].class));
    }

    @Test
    void newVerifiedOwnerMappingPersistsOnlyIssuerSubjectAndOwner() {
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenReturn(List.of());
        assertThat(links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT)).isTrue();
        verify(db).update(startsWith("INSERT INTO prp_mcp_identity_links"),
            eq(ISSUER), eq(SUBJECT), eq(7L));
    }

    @Test
    void existingExactMappingIsIdempotent() {
        when(db.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class),
                      any(), any())).thenAnswer(invocation -> {
            String sql = invocation.getArgument(0);
            return sql.contains("WHERE issuer=? AND subject=?") ?
                List.of(7L) : List.of(SUBJECT);
        });
        assertThat(links.linkFirstPartyOwner(7L, ISSUER, SUBJECT, CHATGPT)).isFalse();
        verify(db, never()).update(anyString(), any(Object[].class));
    }
}
