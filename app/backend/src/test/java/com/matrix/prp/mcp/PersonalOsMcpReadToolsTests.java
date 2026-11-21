package com.matrix.prp.mcp;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.goals.GoalService;
import com.matrix.prp.memory.PersonalMemoryService;
import com.matrix.prp.ontology.PersonalOntology;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.service.TaskService;
import com.matrix.prp.wellness.WellnessService;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.server.ResponseStatusException;

/** Synthetic only. No personal facts, production DB or external OAuth calls. */
class PersonalOsMcpReadToolsTests {
    private final McpScopeGuard guard = mock(McpScopeGuard.class);
    private final GoalService goals = mock(GoalService.class);
    private final PersonalMemoryService memories = mock(PersonalMemoryService.class);
    private final PrpMcpTools tools = new PrpMcpTools(mock(TaskService.class),
        mock(FinanceService.class), mock(WellnessService.class),
        mock(RecordService.class), mock(McpDraftService.class), guard);

    PersonalOsMcpReadToolsTests() {
        ReflectionTestUtils.setField(tools, "personalGoals", goals);
        ReflectionTestUtils.setField(tools, "personalMemories", memories);
    }
    private void owner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    private static GoalService.Goal goal(long id, String domain) {
        return new GoalService.Goal(id,"Synthetic career objective",
            "PRIVATE DESCRIPTION NOT FOR MCP",domain,"ACTIVE","medium",
            "PRIVATE SUCCESS DETAILS NOT FOR MCP",null,LocalDateTime.now(),LocalDateTime.now());
    }
    private static PersonalMemoryService.Memory memory(long id, long user,
        String value, String status, String sensitivity, LocalDate until) {
        return new PersonalMemoryService.Memory(id, PersonalOntology.NodeType.PERSON,
            Long.toString(user),PersonalOntology.Relation.DECLARES_SKILL,
            PersonalOntology.NodeType.LITERAL,null,value,
            com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT,
            null,"USER_CONFIRMED",status,sensitivity,null,until,null,LocalDateTime.now());
    }

    @Test void separateOAuthScopeAndBothOptInsRequiredForAdvertisement() {
        assertThat(McpToolConfiguration.exposedNames("prp.personal_os.read",false)).isEmpty();
        assertThat(McpToolConfiguration.exposedNames("prp.personal_os.read",false,true)).isEmpty();
        assertThat(McpToolConfiguration.exposedNames("prp.personal_os.read",false,false,true)).isEmpty();
        assertThat(McpToolConfiguration.exposedNames("prp.personal_os.read",false,true,true))
            .containsExactlyInAnyOrder("prp_goals_list","prp_goal_context","prp_memory_search");
        assertThat(McpToolConfiguration.exposedNames("prp.wellness.read",false,true,true))
            .doesNotContain("prp_goals_list","prp_goal_context","prp_memory_search");
        assertThat(McpOAuthMetadataController.parseAdvertisedScopes("prp.tasks.read",false))
            .doesNotContain("prp.personal_os.read");
    }

    @Test void missingPersonalScopeStopsReadsBeforeServiceCall() {
        owner(7);
        doThrow(new ResponseStatusException(HttpStatus.FORBIDDEN))
            .when(guard).require("prp.personal_os.read");
        assertThatThrownBy(tools::personalGoalsList).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> tools.personalGoalContext(51)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> tools.personalMemorySearch("Java")).isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(goals,memories);
    }

    @Test void goalListReturnsCareerOnlyAndNeverRawDescriptions() {
        owner(7);
        when(goals.list()).thenReturn(List.of(goal(51,"career"),goal(52,"wellness")));
        @SuppressWarnings("unchecked")
        var items=(List<PrpMcpTools.PersonalGoalSummary>) tools.personalGoalsList();
        assertThat(items).hasSize(1);
        assertThat(items.getFirst().id()).isEqualTo(51);
        assertThat(items.getFirst().title()).isEqualTo("Synthetic career objective");
        assertThat(items.toString()).doesNotContain("PRIVATE DESCRIPTION","PRIVATE SUCCESS");
        verify(goals).list();
        verifyNoInteractions(memories);
    }

    @Test void foreignGoalIsUnavailableAndNoOtherSourceRead() {
        owner(7);
        when(goals.get(99)).thenThrow(new ResponseStatusException(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> tools.personalGoalContext(99))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verify(goals,never()).context(anyLong());
        verifyNoInteractions(memories);
    }

    @Test void ownedGoalContextDoesNotDereferenceRecordOrTaskBody() {
        owner(7);
        when(goals.get(51)).thenReturn(goal(51,"career"));
        when(goals.context(51)).thenReturn(List.of(
            new GoalService.Link(5,"NEEDS_SKILL","GOAL","51","LITERAL",null,"Synthetic Java"),
            new GoalService.Link(6,"ADVANCES","TASK","17","GOAL","51",null),
            new GoalService.Link(7,"UNREVIEWED","GOAL","51","LITERAL",null,"PRIVATE RAW"),
            new GoalService.Link(8,"USES_RESOURCE_RECORD","GOAL","51","RECORD","23",null)));
        @SuppressWarnings("unchecked")
        var items=(List<PrpMcpTools.PersonalGoalEvidence>) tools.personalGoalContext(51);
        assertThat(items).hasSize(3);
        assertThat(items).extracting(PrpMcpTools.PersonalGoalEvidence::assertionId)
            .containsExactly(5L,6L,8L);
        assertThat(items.toString()).doesNotContain("PRIVATE RAW");
        verify(goals).get(51);
        verify(goals).context(51);
        verifyNoInteractions(memories);
    }

    @Test void memorySearchRejectsUnconfirmedRestrictedExpiredAndForeignValues() {
        owner(7);
        when(memories.listCurrent()).thenReturn(List.of(
            memory(11,7,"Synthetic Java", "CONFIRMED","NORMAL",null),
            memory(12,8,"Java foreign", "CONFIRMED","NORMAL",null),
            memory(13,7,"Java draft", "PENDING","NORMAL",null),
            memory(14,7,"Java restricted", "CONFIRMED","RESTRICTED",null),
            memory(15,7,"Java expired", "CONFIRMED","NORMAL",LocalDate.now().minusDays(1)),
            memory(16,7,"Other fact", "CONFIRMED","NORMAL",null)));
        @SuppressWarnings("unchecked")
        var result=(List<PrpMcpTools.PersonalMemorySummary>) tools.personalMemorySearch("Java");
        assertThat(result).singleElement()
            .satisfies(x -> assertThat(x.assertionId()).isEqualTo(11L));
        assertThat(result.toString()).doesNotContain("foreign","draft","restricted","expired");
        verify(memories).listCurrent();
        verifyNoInteractions(goals);
    }

    @Test void emptyKeywordDoesNotQueryMemory() {
        owner(7);
        for(String keyword:List.of(" ","\n","\t","x".repeat(65))) {
            assertThatThrownBy(() -> tools.personalMemorySearch(keyword))
                .isInstanceOf(ResponseStatusException.class);
        }
        verifyNoInteractions(memories);
    }
}
