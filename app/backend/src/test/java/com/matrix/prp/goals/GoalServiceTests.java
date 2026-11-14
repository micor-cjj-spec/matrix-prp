package com.matrix.prp.goals;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.ontology.PersonalOntology.GoalStatus;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

class GoalServiceTests {
    private final JdbcTemplate db=mock(JdbcTemplate.class);
    private final PersonalOntologyReferenceGuard guard=mock(PersonalOntologyReferenceGuard.class);
    private final GoalService service=new GoalService(db,guard);

    private void user(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void clear() {SecurityContextHolder.clearContext();}

    @Test void rejectsInvalidUserInputBeforeDatabaseAccess() {
        user(7);
        assertThatThrownBy(() -> service.create(new GoalService.Create(
            "  ","", "career", "high", null,null,"req_1234567")))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> service.create(new GoalService.Create(
            "Career",null,"../../foo","high",null,null,"req_1234567")))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }

    @Test void listAlwaysUsesAuthenticatedTenant() {
        user(7);
        assertThat(service.list()).isEmpty();
        verify(db).query(contains("user_id=? AND deleted=0"),any(org.springframework.jdbc.core.RowMapper.class),eq(7L));
        verifyNoInteractions(guard);
    }

    @Test void goalStatusTransitionsAreBounded() {
        assertThat(GoalService.allowed(GoalStatus.PLANNED,GoalStatus.ACTIVE)).isTrue();
        assertThat(GoalService.allowed(GoalStatus.ACTIVE,GoalStatus.PAUSED)).isTrue();
        assertThat(GoalService.allowed(GoalStatus.PAUSED,GoalStatus.ACTIVE)).isTrue();
        assertThat(GoalService.allowed(GoalStatus.ACTIVE,GoalStatus.COMPLETED)).isTrue();
        assertThat(GoalService.allowed(GoalStatus.COMPLETED,GoalStatus.ACTIVE)).isFalse();
        assertThat(GoalService.allowed(GoalStatus.CANCELLED,GoalStatus.ACTIVE)).isFalse();
    }

    @Test void rejectsAnonymousListAndNonPositiveGoalIds() {
        assertThatThrownBy(service::list)
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        user(7);
        assertThatThrownBy(() -> service.get(-1))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }
}
