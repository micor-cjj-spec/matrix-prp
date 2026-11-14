package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.goals.GoalService;
import com.matrix.prp.memory.PersonalMemoryService;
import com.matrix.prp.ontology.PersonalOntology.NodeType;
import com.matrix.prp.ontology.PersonalOntology.Relation;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

class PersonalOsPlanningPreviewServiceTest {
    private final GoalService goals = mock(GoalService.class);
    private final PersonalMemoryService memories = mock(PersonalMemoryService.class);
    private final PersonalOsPlanningPreviewService service =
        new PersonalOsPlanningPreviewService(goals, memories);

    private void user(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    private GoalService.Goal goal(long id) {
        return new GoalService.Goal(id, "Synthetic career goal", null, "career",
            "ACTIVE", "medium", null, null, LocalDateTime.now(), LocalDateTime.now());
    }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void unauthenticatedRequestNeverReadsBusinessServices() {
        assertThatThrownBy(() -> service.preview(1,true))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        verifyNoInteractions(goals,memories);
    }

    @Test void defaultPreviewDoesNotReadPersonalMemoryOrCallModelOrWrite() {
        user(7);
        when(goals.get(51)).thenReturn(goal(51));
        when(goals.context(51)).thenReturn(List.of());
        var preview=service.preview(51,false);
        assertThat(preview.modelInvoked()).isFalse();
        assertThat(preview.dataWritten()).isFalse();
        assertThat(preview.evidence()).extracting(PersonalOsPlanningPreviewService.Evidence::reference)
            .containsExactly("goal:51");
        assertThat(preview.gaps()).extracting(PersonalOsPlanningPreviewService.Gap::code)
            .contains("PERSONAL_FACTS_NOT_SELECTED","TASK_RELATION_UNRECORDED",
                "SKILL_REQUIREMENTS_UNRECORDED","SUCCESS_CRITERIA_UNSPECIFIED");
        assertThat(preview.taskDrafts()).hasSize(3);
        verifyNoInteractions(memories);
        verify(goals).get(51);
        verify(goals).context(51);
        verifyNoMoreInteractions(goals);
    }

    @Test void personalPreviewAcceptsOnlyCurrentNormalOwnerConfirmedLiterals() {
        user(7);
        when(goals.get(51)).thenReturn(goal(51));
        when(goals.context(51)).thenReturn(List.of(
            new GoalService.Link(9,"NEEDS_SKILL","GOAL","51","LITERAL",null,"Synthetic Java")));
        var confirmed = new PersonalMemoryService.Memory(11,NodeType.PERSON,"7",
            Relation.DECLARES_SKILL,NodeType.LITERAL,null,"Synthetic Spring",
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"USER_CONFIRMED","CONFIRMED","NORMAL",null,null,null,LocalDateTime.now());
        var foreign = new PersonalMemoryService.Memory(12,NodeType.PERSON,"8",
            Relation.DECLARES_SKILL,NodeType.LITERAL,null,"Foreign data",
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"USER_CONFIRMED","CONFIRMED","NORMAL",null,null,null,LocalDateTime.now());
        var pending = new PersonalMemoryService.Memory(13,NodeType.PERSON,"7",
            Relation.PREFERS,NodeType.LITERAL,null,"Not confirmed",
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"AI_CANDIDATE","PENDING","NORMAL",null,null,null,LocalDateTime.now());
        var restricted = new PersonalMemoryService.Memory(14,NodeType.PERSON,"7",
            Relation.HAS_BACKGROUND,NodeType.LITERAL,null,"Private",
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"USER_CONFIRMED","CONFIRMED","RESTRICTED",null,null,null,LocalDateTime.now());
        var expired = new PersonalMemoryService.Memory(15,NodeType.PERSON,"7",
            Relation.PREFERS,NodeType.LITERAL,null,"Expired",
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"USER_CONFIRMED","CONFIRMED","NORMAL",null,LocalDate.now().minusDays(1),
            null,LocalDateTime.now());
        when(memories.listCurrent()).thenReturn(List.of(confirmed,foreign,pending,restricted,expired));
        var preview=service.preview(51,true);
        assertThat(preview.evidence()).extracting(PersonalOsPlanningPreviewService.Evidence::reference)
            .containsExactly("goal:51","assertion:9","assertion:11");
        assertThat(preview.taskDrafts()).hasSize(2); // skill requirement is present
        verify(memories).listCurrent();
        verifyNoMoreInteractions(memories);
    }

    @Test void ownerLookupDenialCannotFallBackToPersonalData() {
        user(7);
        when(goals.get(99)).thenThrow(new ResponseStatusException(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> service.preview(99,true))
            .isInstanceOf(ResponseStatusException.class);
        verify(goals).get(99);
        verifyNoInteractions(memories);
        verify(goals,never()).context(anyLong());
    }

    @Test void closedGoalHasNoActionDraftsAndNeverDereferencesRecordText() {
        user(7);
        GoalService.Goal old=goal(51);
        when(goals.get(51)).thenReturn(new GoalService.Goal(old.id(),old.title(),
            old.description(),old.domain(),"COMPLETED",old.priority(),
            "Synthetic criteria",null,old.createdAt(),old.updatedAt()));
        when(goals.context(51)).thenReturn(List.of(new GoalService.Link(
            19,"USES_RESOURCE_RECORD","GOAL","51","RECORD","888",null)));
        var preview=service.preview(51,false);
        assertThat(preview.taskDrafts()).isEmpty();
        assertThat(preview.evidence()).extracting(PersonalOsPlanningPreviewService.Evidence::statement)
            .contains("RECORD #888").doesNotContain("Synthetic record body");
        verifyNoInteractions(memories);
    }

    @Test void nonCareerDomainIsNotIncludedInPilot() {
        user(7);
        GoalService.Goal old=goal(51);
        when(goals.get(51)).thenReturn(new GoalService.Goal(old.id(),old.title(),
            null,"wellness",old.status(),old.priority(),null,null,
            old.createdAt(),old.updatedAt()));
        assertThatThrownBy(() -> service.preview(51,true))
            .isInstanceOf(ResponseStatusException.class);
        verify(goals,never()).context(anyLong());
        verifyNoInteractions(memories);
    }
}
