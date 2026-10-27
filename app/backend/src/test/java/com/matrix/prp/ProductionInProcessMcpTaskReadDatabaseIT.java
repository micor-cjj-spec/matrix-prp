package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.mcp.McpClientGrantService;
import com.matrix.prp.mcp.McpFirstPartyOidcLinkService;
import com.matrix.prp.mcp.McpIdentityLinkService;
import com.matrix.prp.mcp.PrpMcpTools;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.model.TaskItem;
import com.matrix.prp.tasks.service.TaskService;
import java.util.List;
import java.util.OptionalLong;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.server.ResponseStatusException;

/**
 * CI-only proof that PRP's actual OAuth linking/grant storage and MCP
 * task tool can work against the SAME owner-bound PRP task DB.
 *
 * No real HTTP OAuth bearer, no Keycloak network, no production schema,
 * no client installation, no live identity and no server cutover.
 * The "syntheticSignedIdentity" helper represents claims already verified
 * by the independent cryptographic/HTTP E2E; it is NOT a JWT verifier.
 */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties = {
    "matrix-prp.mcp.enabled=true",
    "matrix-prp.mcp.oauth.enabled=true",
    "matrix-prp.mcp.oauth.issuer=https://issuer.example.test",
    "matrix-prp.mcp.oauth.jwk-set-uri=https://issuer.example.test/jwks.json",
    "matrix-prp.mcp.oauth.resource=https://micor.top/api/mcp",
    "matrix-prp.mcp.write-enabled=false",
    "matrix-prp.mcp.oauth.first-party-link.enabled=false",
    "spring.ai.mcp.server.enabled=true",
    "matrix-prp.ai.spring-ai.enabled=false",
    "matrix-prp.ai.spring-ai.tools-enabled=false"
})
class ProductionInProcessMcpTaskReadDatabaseIT {
    private static final String ISSUER = "https://issuer.example.test";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";

    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired McpClientGrantService grants;
    @Autowired McpIdentityLinkService links;
    @Autowired TaskService tasks;
    @Autowired PrpMcpTools mcp;

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    private UserAccount createOwner() {
        String username = "ci_inprocess_" + UUID.randomUUID().toString()
            .replace("-", "").substring(0, 15);
        return users.create(username, "Synthetic owner", passwords.encode("disposable-pass"), false);
    }

    private void firstPartySession(UserAccount account) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(account.profile(), null, List.of()));
    }

    private void linkFromVerifiedSyntheticIssuer(UserAccount owner, String subject) {
        firstPartySession(owner);
        grants.authorize(CLIENT, List.of("prp.tasks.read"), "disposable-pass");
        var ticket = links.issueTicket(CLIENT, "disposable-pass");
        // The test injects a synthetic already-verified (iss, sub, client).
        // Actual signature verification is separately tested.
        links.complete(ticket.code(), ISSUER, subject, CLIENT);
        assertThat(links.resolveUserId(ISSUER, subject)).hasValue(owner.id());
    }

    private void syntheticSignedIdentity(String subject, boolean includeTaskScope) {
        SecurityContextHolder.clearContext();
        OptionalLong ownerId = links.resolveUserId(ISSUER, subject);
        if (ownerId.isEmpty()) throw new SecurityException("No verified PRP identity link");
        UserAccount owner = users.findById(ownerId.getAsLong())
            .orElseThrow(() -> new SecurityException("PRP owner unavailable"));
        if (!owner.enabled()) throw new SecurityException("PRP owner disabled");
        Set<String> approved = grants.grantedScopes(owner.id(), CLIENT);
        if (!approved.contains("prp.tasks.read"))
            throw new SecurityException("Client task-read grant revoked");
        var authorities = includeTaskScope
            ? List.of(new SimpleGrantedAuthority("SCOPE_prp.tasks.read"))
            : List.<SimpleGrantedAuthority>of();
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(owner.profile(), null, authorities));
    }

    @SuppressWarnings("unchecked")
    private List<TaskItem> list() {
        return (List<TaskItem>) mcp.listTasks(null);
    }

    @Test
    void linkedOauthOwnersReadTheirOwnExistingTaskStoreWithoutAnyBridge() {
        UserAccount alice = createOwner();
        UserAccount bob = createOwner();
        String aliceSubject = "ci-alice-" + UUID.randomUUID();
        String bobSubject = "ci-bob-" + UUID.randomUUID();

        firstPartySession(alice);
        for (int i = 0; i < 24; i++) {
            tasks.create(new CreateTaskRequest("work", "CI-inprocess-A-" + i,
                "synthetic task", "low", null));
        }
        firstPartySession(bob);
        for (int i = 0; i < 3; i++) {
            tasks.create(new CreateTaskRequest("work", "CI-inprocess-B-" + i,
                "synthetic task", "low", null));
        }
        linkFromVerifiedSyntheticIssuer(alice, aliceSubject);
        linkFromVerifiedSyntheticIssuer(bob, bobSubject);

        syntheticSignedIdentity(aliceSubject, true);
        assertThat(list()).hasSize(20).allSatisfy(
            task -> assertThat(task.title()).startsWith("CI-inprocess-A-"));

        syntheticSignedIdentity(bobSubject, true);
        assertThat(list()).hasSize(3).allSatisfy(
            task -> assertThat(task.title()).startsWith("CI-inprocess-B-"));

        // OAuth issuer/subject cannot be mapped to the other local owner.
        assertThat(links.resolveUserId(ISSUER, aliceSubject)).hasValue(alice.id());
        assertThat(links.resolveUserId(ISSUER, bobSubject)).hasValue(bob.id());

        // PRP owner revocation applies on the NEXT simulated OAuth request:
        firstPartySession(alice);
        grants.revoke(CLIENT);
        assertThatThrownBy(() -> syntheticSignedIdentity(aliceSubject, true))
            .isInstanceOf(SecurityException.class);
        SecurityContextHolder.clearContext();
        assertThatThrownBy(this::list).isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        syntheticSignedIdentity(bobSubject, true);
        assertThat(list()).hasSize(3);
    }

    @Test
    void missingScopeOrUnlinkedSubjectCannotQueryTheTaskTool() {
        UserAccount owner = createOwner();
        String subject = "ci-unlinked-" + UUID.randomUUID();
        firstPartySession(owner);
        grants.authorize(CLIENT, List.of("prp.tasks.read"), "disposable-pass");
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> syntheticSignedIdentity(subject, true))
            .isInstanceOf(SecurityException.class);

        linkFromVerifiedSyntheticIssuer(owner, subject);
        syntheticSignedIdentity(subject, false);
        assertThatThrownBy(this::list).isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN));
    }
}
