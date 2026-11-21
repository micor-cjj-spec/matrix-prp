package com.matrix.prp.mcp;

import static org.assertj.core.api.Assertions.*;

import com.matrix.prp.auth.model.UserProfile;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/** Real scope guard logic using synthetic verified client identities only. */
class PersonalOsMcpScopeGuardTests {
    private static final String SCOPE = "prp.personal_os.read";
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";

    private void auth(long owner, String client, boolean grantedAuthority, boolean consentSnapshot) {
        var token = new UsernamePasswordAuthenticationToken(
            new UserProfile(owner, "synthetic", "Synthetic"), null,
            grantedAuthority ? List.of(new SimpleGrantedAuthority("SCOPE_" + SCOPE)) : List.of());
        token.setDetails(new McpScopeGuard.VerifiedClient(client,
            consentSnapshot ? Set.of(SCOPE) : Set.of()));
        SecurityContextHolder.getContext().setAuthentication(token);
    }

    @AfterEach void clean() { SecurityContextHolder.clearContext(); }

    @Test void positiveCaseRequiresAllowedOwnerClientAndExactTokenScope() {
        var guard = new McpScopeGuard(true);
        guard.configureExpandedUsers("7",CLIENT);
        auth(7,CLIENT,true,true);
        assertThatCode(() -> guard.require(SCOPE)).doesNotThrowAnyException();
    }

    @Test void ownerOutsideExpandedAllowlistIsDenied() {
        var guard = new McpScopeGuard(true);
        guard.configureExpandedUsers("7",CLIENT);
        auth(8,CLIENT,true,true);
        assertThatThrownBy(() -> guard.require(SCOPE))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(err -> assertThat(((ResponseStatusException)err).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test void wrongOAuthClientIsDeniedEvenWithMatchingScope() {
        var guard = new McpScopeGuard(true);
        guard.configureExpandedUsers("7",CLIENT);
        auth(7,"synthetic-untrusted-client",true,true);
        assertThatThrownBy(() -> guard.require(SCOPE))
            .isInstanceOf(ResponseStatusException.class);
    }

    @Test void noEffectiveOwnerConsentCannotBePromotedToAuthority() {
        var guard = new McpScopeGuard(true);
        guard.configureExpandedUsers("7",CLIENT);
        // The production OAuth converter builds authorities only from
        // token scopes intersected with current database owner grants.
        auth(7,CLIENT,false,false);
        assertThatThrownBy(() -> guard.require(SCOPE))
            .isInstanceOf(ResponseStatusException.class);
    }

    @Test void existingTaskScopeDoesNotImplyPersonalOsPermission() {
        var guard = new McpScopeGuard(true);
        guard.configureExpandedUsers("7",CLIENT);
        var token = new UsernamePasswordAuthenticationToken(
            new UserProfile(7,"synthetic","Synthetic"),null,
            List.of(new SimpleGrantedAuthority("SCOPE_prp.tasks.read")));
        token.setDetails(new McpScopeGuard.VerifiedClient(CLIENT,Set.of("prp.tasks.read")));
        SecurityContextHolder.getContext().setAuthentication(token);
        assertThatThrownBy(() -> guard.require(SCOPE))
            .isInstanceOf(ResponseStatusException.class);
    }
}
