package com.matrix.prp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.mcp.McpClientGrantService;
import com.matrix.prp.mcp.McpIdentityLinkService;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Real MySQL: one-use ticket, token-bound client, and issuer/sub mapping. */
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
class McpIdentityLinkDatabaseIT {
    private static final String ISSUER = "https://issuer.example.test";
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired McpClientGrantService grants;
    @Autowired McpIdentityLinkService links;
    @Autowired JdbcTemplate jdbc;

    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    private UserAccount user(String password) {
        return users.create("mcp_identity_" + UUID.randomUUID().toString().replace("-", "").substring(0, 14),
            "OAuth link test", passwords.encode(password), false);
    }

    private void as(UserAccount u) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(u.profile(), null, List.of()));
    }

    @Test
    void matchingBearerSubjectLinksOnceWithoutTrustingClaimsAboutUserId() {
        String pass = "prp-owner-test-2026";
        UserAccount owner = user(pass), stranger = user("other-" + pass);
        String client = "ci-client-" + UUID.randomUUID();
        String subject = "issuer-user-" + UUID.randomUUID();
        as(owner);
        grants.authorize(client, List.of("prp.tasks.read"), pass);
        var ticket = links.issueTicket(client, pass);
        assertThat(ticket.code()).hasSize(43);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM prp_mcp_link_tickets WHERE ticket_hash=?",
            Integer.class, ticket.code())).isZero();

        assertThatThrownBy(() -> links.complete(ticket.code(), ISSUER, subject, "different-client"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
        assertThat(links.resolveUserId(ISSUER, subject)).isEmpty();

        var linked = links.complete(ticket.code(), ISSUER, subject, client);
        assertThat(linked.newlyLinked()).isTrue();
        assertThat(links.resolveUserId(ISSUER, subject)).hasValue(owner.id());
        assertThatThrownBy(() -> links.complete(ticket.code(), ISSUER, subject, client))
            .isInstanceOf(ResponseStatusException.class);

        as(stranger);
        assertThat(links.myLinks()).isEmpty();
        grants.authorize(client, List.of("prp.tasks.read"), "other-" + pass);
        var strangerTicket = links.issueTicket(client, "other-" + pass);
        assertThatThrownBy(() -> links.complete(strangerTicket.code(), ISSUER, subject, client))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
        assertThat(links.resolveUserId(ISSUER, subject)).hasValue(owner.id());

        as(owner);
        links.unlink(pass);
        assertThat(links.resolveUserId(ISSUER, subject)).isEmpty();
    }

    @Test
    void expiredOrRevokedTicketsNeverEstablishIdentity() {
        String pass = "identity-expire-2026";
        UserAccount owner = user(pass);
        String client = "expiry-" + UUID.randomUUID();
        String subject = "subject-" + UUID.randomUUID();
        as(owner);
        grants.authorize(client, List.of("prp.tasks.read"), pass);
        var expired = links.issueTicket(client, pass);
        jdbc.update("UPDATE prp_mcp_link_tickets SET expires_at=DATE_SUB(NOW(),INTERVAL 1 SECOND) WHERE user_id=?",
            owner.id());
        assertThatThrownBy(() -> links.complete(expired.code(), ISSUER, subject, client))
            .isInstanceOf(ResponseStatusException.class);
        var revoked = links.issueTicket(client, pass);
        grants.revoke(client);
        assertThatThrownBy(() -> links.complete(revoked.code(), ISSUER, subject, client))
            .isInstanceOf(ResponseStatusException.class);
        assertThat(links.resolveUserId(ISSUER, subject)).isEmpty();
    }
}
