package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.security.LoginAttemptLimiter;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class McpProductionWellnessReadExtensionTests {
    private static final String JDBC="jdbc:mysql://127.0.0.1:3306/matrix_prp";
    private static final String RESOURCE="https://micor.top/api/mcp";
    private static final String ISSUER="https://auth.micor.top/realms/prp-mcp-prod";
    private static final String OWNER="77";
    private static final String HEALTH=String.join(",",McpProductionWellnessGuard.SCOPES);
    private static final String EXPANDED=HEALTH+",prp.tasks.read,prp.records.read,prp.practice.read";

    void check(String scopes,boolean extension,boolean tools) {
        McpProductionWellnessGuard.verify(true,true,true,false,false,scopes,JDBC,RESOURCE,ISSUER,
            OWNER,extension,tools);
    }

    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void defaultHealthModeStillAcceptsExactlySixHealthScopes() {
        assertThatCode(()->check(HEALTH,false,false)).doesNotThrowAnyException();
        assertThatCode(()->check(HEALTH,false,true)).doesNotThrowAnyException();
        assertThatThrownBy(()->check(EXPANDED,false,true)).isInstanceOf(IllegalStateException.class);
    }

    @Test void extraScopesNeedBothOptInFlagsAndExactReadAllowlist() {
        assertThatCode(()->check(EXPANDED,true,true)).doesNotThrowAnyException();
        assertThatThrownBy(()->check(EXPANDED,true,false)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->check(HEALTH,true,true)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->check(EXPANDED+",prp.finance.read",true,true))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->check(EXPANDED+",prp.write.create",true,true))
            .isInstanceOf(IllegalStateException.class);
    }

    @Test void extensionCannotBypassExistingHealthDbIssuerOrWriteGuards() {
        // Invalid write-enabled=false + wellness write scopes is rejected by scope parsing first.
        assertThatThrownBy(()->McpProductionWellnessGuard.verify(true,true,false,false,false,EXPANDED,
            JDBC,RESOURCE,ISSUER,OWNER,true,true)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->McpProductionWellnessGuard.verify(true,true,true,true,false,EXPANDED,
            JDBC,RESOURCE,ISSUER,OWNER,true,true)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->McpProductionWellnessGuard.verify(true,true,true,false,false,EXPANDED,
            "jdbc:mysql://203.0.113.7/matrix_prp",RESOURCE,ISSUER,OWNER,true,true))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->McpProductionWellnessGuard.verify(true,true,true,false,false,EXPANDED,
            JDBC,RESOURCE,"https://auth-test.micor.top/realms/prp-mcp",OWNER,true,true))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->McpProductionWellnessGuard.verify(true,true,true,false,false,EXPANDED,
            JDBC,RESOURCE,ISSUER,"",true,true)).isInstanceOf(IllegalStateException.class);
    }

    @Test void consentIsRestrictedToHealthAndThreeReadScopesWithoutWeakeningPasswordCheck() {
        assertThat(McpProductionWellnessGuard.consentScopes(false))
            .containsExactlyInAnyOrderElementsOf(McpProductionWellnessGuard.SCOPES);
        assertThat(McpProductionWellnessGuard.consentScopes(true))
            .containsAll(McpProductionWellnessGuard.SCOPES)
            .containsAll(Set.of("prp.tasks.read","prp.records.read","prp.practice.read"))
            .doesNotContain("prp.finance.read","prp.write.create","prp.write.confirm");

        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
            new UserProfile(77,"synthetic","Synthetic"),null,List.of()));
        var db=mock(JdbcTemplate.class);
        var grant=new McpClientGrantService(db,mock(UserStore.class),
            mock(PasswordEncoder.class),mock(LoginAttemptLimiter.class));
        grant.configureWellnessOnly(true,false);
        assertThatThrownBy(()->grant.authorize("https://chatgpt.com/oauth/client.json",
            List.of("prp.practice.read"),"unused"))
            .isInstanceOf(ResponseStatusException.class).satisfies(e->
                assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN));
        grant.configureWellnessOnly(true,true);
        // Scope passes allowlist; no fake account means owner authentication still rejects it.
        assertThatThrownBy(()->grant.authorize("https://chatgpt.com/oauth/client.json",
            List.of("prp.practice.read"),"unused"))
            .isInstanceOf(ResponseStatusException.class).satisfies(e->
                assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED));
        assertThatThrownBy(()->grant.authorize("https://chatgpt.com/oauth/client.json",
            List.of("prp.finance.read"),"unused"))
            .isInstanceOf(ResponseStatusException.class).satisfies(e->
                assertThat(((ResponseStatusException)e).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN));
        verifyNoInteractions(db);
        assertThatThrownBy(()->grant.configureWellnessOnly(false,true))
            .isInstanceOf(IllegalStateException.class);
    }
}
