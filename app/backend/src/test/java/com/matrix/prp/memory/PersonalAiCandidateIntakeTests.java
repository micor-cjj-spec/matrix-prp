package com.matrix.prp.memory;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.ontology.PersonalOntology.Sensitivity;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/** Synthetic T-008a provenance and review-state regression; no real private data. */
class PersonalAiCandidateIntakeTests {
    private final JdbcTemplate db = mock(JdbcTemplate.class);
    private final PersonalOntologyReferenceGuard references =
        mock(PersonalOntologyReferenceGuard.class);
    private final PersonalMemoryService memory = new PersonalMemoryService(db,references);
    private final PersonalAiCandidateIntakeService batch =
        new PersonalAiCandidateIntakeService(memory);

    private void owner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    private static PersonalMemoryService.AiCandidate skill(String key) {
        return new PersonalMemoryService.AiCandidate(
            DECLARES_SKILL,"Synthetic Java",null,null,null,key);
    }

    @Test void untrustedRelationsAndMalformedValuesFailBeforeDatabaseAccess() {
        owner(7);
        var bad = List.of(
            new PersonalMemoryService.AiCandidate(REQUIRES,"Synthetic Java",null,null,null,"candidate-01"),
            new PersonalMemoryService.AiCandidate(null,"Synthetic Java",null,null,null,"candidate-02"),
            new PersonalMemoryService.AiCandidate(DECLARES_SKILL,"  ",null,null,null,"candidate-03"),
            new PersonalMemoryService.AiCandidate(DECLARES_SKILL,"value\nwith control",null,null,null,"candidate-04"),
            new PersonalMemoryService.AiCandidate(DECLARES_SKILL,"x".repeat(257),null,null,null,"candidate-05")
        );
        for (var c:bad) {
            assertThatThrownBy(() -> memory.proposeAiCandidate(c))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                    .isEqualTo(HttpStatus.BAD_REQUEST));
        }
        verifyNoInteractions(db,references);
    }

    @Test void anonymousCannotSubmitCandidate() {
        assertThatThrownBy(() -> batch.submit(List.of(skill("candidate-06"))))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        verifyNoInteractions(db,references);
    }

    @Test void batchRefusesEmptyOversizeAndDuplicateKeysBeforeWrites() {
        owner(7);
        assertThatThrownBy(() -> batch.submit(List.of())).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> batch.submit(List.of(
            skill("candidate-07"),skill("candidate-07"))))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> batch.submit(List.of(
            skill("candidate-01"),skill("candidate-02"),skill("candidate-03"),
            skill("candidate-04"),skill("candidate-05"),skill("candidate-06"))))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> batch.submit(Arrays.asList(skill("candidate-07"), null)))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db,references);
    }

    @Test void modelCandidateIsPersistedWithAiOriginRestrictedDefaultAndPendingState() throws Exception {
        owner(7);
        when(db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE", Long.class, 7L))
            .thenReturn(7L);
        doAnswer(invocation -> {
            PreparedStatementCreator creator = invocation.getArgument(0);
            Connection connection=mock(Connection.class);
            PreparedStatement ps=mock(PreparedStatement.class);
            when(connection.prepareStatement(anyString(),eq(Statement.RETURN_GENERATED_KEYS)))
                .thenReturn(ps);
            creator.createPreparedStatement(connection);
            verify(ps).setLong(1,7L);
            verify(ps).setString(2,"PERSON");
            verify(ps).setString(4,"DECLARES_SKILL");
            verify(ps).setString(5,"LITERAL");
            verify(ps).setString(8,"USER_INPUT");
            verify(ps).setString(10,"AI_CANDIDATE");
            verify(ps).setString(11,"RESTRICTED");
            verify(connection).prepareStatement(contains("'PENDING'"),
                eq(Statement.RETURN_GENERATED_KEYS));
            throw new IllegalStateException("Synthetic DB boundary reached");
        }).when(db).update(any(PreparedStatementCreator.class),any(KeyHolder.class));

        assertThatThrownBy(() -> batch.submit(List.of(skill("candidate-08"))))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("Synthetic DB boundary reached");
        verify(references).requireOwned(PERSON,"7");
    }

    @Test void originSpoofUsingPreviouslyUserSubmittedRequestKeyIsRejected() {
        owner(7);
        var old = new PersonalMemoryService.Memory(
            41L,PERSON,"7",DECLARES_SKILL,LITERAL,null,"Synthetic Java",USER_INPUT,
            null,"USER_CONFIRMED","PENDING","RESTRICTED",null,null,null,LocalDateTime.now());
        var proposed = new PersonalMemoryService.Proposed(
            PERSON,"7",DECLARES_SKILL,LITERAL,null,"Synthetic Java",USER_INPUT,
            null,null,null,Sensitivity.RESTRICTED,"candidate-09");
        assertThatThrownBy(() -> PersonalMemoryService.matchingReplay(
            old,proposed,null,"AI_CANDIDATE"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        // Exact same payload and origin may be idempotently returned instead.
        var ai = new PersonalMemoryService.Memory(
            41L,PERSON,"7",DECLARES_SKILL,LITERAL,null,"Synthetic Java",USER_INPUT,
            null,"AI_CANDIDATE","PENDING","RESTRICTED",null,null,null,LocalDateTime.now());
        assertThat(PersonalMemoryService.matchingReplay(ai,proposed,null,"AI_CANDIDATE"))
            .isSameAs(ai);
        verifyNoInteractions(db,references);
    }
}
