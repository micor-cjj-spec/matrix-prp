package com.matrix.prp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.mcp.McpClientGrantService;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** A real MySQL and password-verification check, not a mock of grants. */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "spring.ai.mcp.server.enabled=true"
})
class McpClientGrantDatabaseIT {
    @Autowired McpClientGrantService grants;
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;

    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    private UserAccount create(String password) {
        return users.create("oauth_grant_" + UUID.randomUUID().toString().replace("-", "").substring(0, 16),
            "OAuth test user", passwords.encode(password), false);
    }
    private void as(UserAccount account) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(account.profile(), null, List.of()));
    }

    @Test
    void grantScopesAreOwnerBoundImmediatelyRevocableAndCanBeReduced() {
        String pass = "owner-ci-pass-2026";
        UserAccount owner = create(pass), stranger = create("not-" + pass);
        String clientId = "test-client-" + UUID.randomUUID();
        as(owner);
        assertThat(grants.grantedScopes(owner.id(), clientId)).isEmpty();
        assertThatThrownBy(() -> grants.authorize(clientId, List.of("prp.tasks.read"), "wrong"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException) e).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThat(grants.grantedScopes(owner.id(), clientId)).isEmpty();

        var created = grants.authorize(clientId,
            List.of("prp.tasks.read", "prp.finance.read", "prp.write.create"), pass);
        assertThat(created.status()).isEqualTo("ACTIVE");
        assertThat(grants.grantedScopes(owner.id(), clientId))
            .containsExactlyInAnyOrder("prp.tasks.read", "prp.finance.read", "prp.write.create");
        assertThat(grants.grantedScopes(stranger.id(), clientId)).isEmpty();

        as(stranger);
        grants.revoke(clientId);
        assertThat(grants.grantedScopes(owner.id(), clientId)).hasSize(3);

        as(owner);
        grants.authorize(clientId, List.of("prp.tasks.read"), pass);
        assertThat(grants.grantedScopes(owner.id(), clientId)).isEqualTo(Set.of("prp.tasks.read"));
        grants.revoke(clientId);
        assertThat(grants.grantedScopes(owner.id(), clientId)).isEmpty();
        assertThat(grants.mine()).extracting(McpClientGrantService.Grant::status).contains("REVOKED");
    }

    @Test
    void rejectsWildcardScopesAndForeignPasswords() {
        String password = "grant-ci-password";
        UserAccount user = create(password);
        as(user);
        assertThatThrownBy(() -> grants.authorize("client-test", List.of("prp.*"), password))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> grants.authorize("client-test",
            List.of("prp.tasks.read", "prp.tasks.read"), password))
            .isInstanceOf(ResponseStatusException.class);
        assertThat(grants.grantedScopes(user.id(), "client-test")).isEmpty();
    }
}
