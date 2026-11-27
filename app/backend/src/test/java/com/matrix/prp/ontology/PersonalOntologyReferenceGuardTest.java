package com.matrix.prp.ontology;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

class PersonalOntologyReferenceGuardTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final PersonalOntologyReferenceGuard guard = new PersonalOntologyReferenceGuard(jdbc);

    private void user(long id) {
        var profile = new UserProfile(id, "synthetic", "Synthetic owner");
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(profile, null, List.of()));
    }

    @AfterEach
    void clearSecurity() { SecurityContextHolder.clearContext(); }

    @Test
    void personReferenceMustBeTheAuthenticatedUser() {
        user(7);
        assertDoesNotThrow(() -> guard.requireOwned(PERSON, "7"));
        var foreign = assertThrows(ResponseStatusException.class,
            () -> guard.requireOwned(PERSON, "8"));
        org.assertj.core.api.Assertions.assertThat(foreign.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        verifyNoInteractions(jdbc);
    }

    @Test
    void databaseEntitiesAreOwnerScoped() {
        user(7);
        when(jdbc.queryForList(anyString(), eq(Integer.class), eq(11L), eq(7L)))
            .thenReturn(List.of(1));
        assertDoesNotThrow(() -> guard.requireOwned(GOAL, "11"));
        var missing = assertThrows(ResponseStatusException.class,
            () -> guard.requireOwned(GOAL, "12"));
        org.assertj.core.api.Assertions.assertThat(missing.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        verify(jdbc).queryForList(contains("prp_goals"),eq(Integer.class),eq(11L),eq(7L));
        verify(jdbc).queryForList(contains("prp_goals"),eq(Integer.class),eq(12L),eq(7L));
    }

    @Test
    void rejectsUnresolvedOrMalformedReferences() {
        user(7);
        for (var unsupported : List.of(SKILL, EVENT, RESOURCE, LITERAL)) {
            var failure = assertThrows(ResponseStatusException.class,
                () -> guard.requireOwned(unsupported, "10"));
            org.assertj.core.api.Assertions.assertThat(failure.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        }
        for (String invalid : List.of("0","-1","0007","12 OR 1=1",
                "99999999999999999999","")) {
            assertThrows(ResponseStatusException.class,
                () -> guard.requireOwned(TASK, invalid));
        }
        verifyNoInteractions(jdbc);
    }

    @Test
    void anonymousContextCannotQueryAnyEntity() {
        var denied = assertThrows(ResponseStatusException.class,
            () -> guard.requireOwned(PERSON, "7"));
        org.assertj.core.api.Assertions.assertThat(denied.getStatusCode())
            .isEqualTo(HttpStatus.UNAUTHORIZED);
        verifyNoInteractions(jdbc);
    }
}
