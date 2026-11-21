package com.matrix.prp.memory;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.ontology.PersonalOntology.Sensitivity;
import com.matrix.prp.ontology.PersonalOntologyAssertionGuard;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.sql.ResultSet;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/** Pure synthetic ownership/provenance/duplicate regressions, no actual conversation data. */
class PersonalKnowledgeEvolutionTests {
    private final JdbcTemplate db=mock(JdbcTemplate.class);
    private final PersonalOntologyReferenceGuard references=mock(PersonalOntologyReferenceGuard.class);
    private final PersonalMemoryService memories=new PersonalMemoryService(db,references);

    private void owner(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    private static PersonalMemoryService.AiCandidate candidate(String value,String key) {
        return new PersonalMemoryService.AiCandidate(DECLARES_SKILL,value,null,null,
            Sensitivity.RESTRICTED,key,91L,"我正在学习 RAG");
    }
    @Test void quotedSourceMustBeOwnerUserMessageAndActuallyContainVerbatimText() {
        owner(7);
        var actual=new PersonalOntologyReferenceGuard(db);
        when(db.queryForList(contains("FROM prp_ai_messages"),eq(String.class),eq(91L),eq(7L)))
            .thenReturn(List.of("我正在学习 RAG，也希望转型 AI FDE。"));
        assertThatCode(() -> actual.requireOwnedChatQuote("91","我正在学习 RAG"))
            .doesNotThrowAnyException();
        assertThatThrownBy(() -> actual.requireOwnedChatQuote("91","我已经掌握 RAG"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST));
        owner(8);
        assertThatThrownBy(() -> actual.requireOwnedChatQuote("91","我正在学习 RAG"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
    }

    @Test void aiEvidenceMustUseSeparateOwnedChatMessageSource() {
        owner(7);
        new PersonalOntologyAssertionGuard(references).requireValid(
            new PersonalOntologyAssertionGuard.Candidate(PERSON,"7",DECLARES_SKILL,
                LITERAL,null,"学习 RAG",CHAT_MESSAGE,"91",null,null));
        verify(references).requireOwned(PERSON,"7");
        verify(references).requireOwnedChatMessage("91");
    }

    @Test void quotedSourceIsRequiredAsPairAndInvalidSourceStopsWrite() {
        owner(7);
        var missingQuote=new PersonalMemoryService.AiCandidate(
            DECLARES_SKILL,"学习 RAG",null,null,null,"synthetic-key-001",91L,null);
        assertThatThrownBy(() -> memories.proposeAiCandidate(missingQuote))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST));
        var proper=candidate("学习 RAG","synthetic-key-002");
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwnedChatQuote("91","我正在学习 RAG");
        assertThatThrownBy(() -> memories.proposeAiCandidate(proper))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verifyNoInteractions(db);
    }

    @Test void normalizedDuplicateFromSameOwnerAndRelationRefusesNewCandidate() throws Exception {
        owner(7);
        when(db.query(contains("SELECT object_value,valid_from,valid_to"),
                any(RowMapper.class),eq(7L),eq("7"),eq("DECLARES_SKILL"),eq(0L)))
            .thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                RowMapper<Object> mapper=invocation.getArgument(1);
                ResultSet rs=mock(ResultSet.class);
                when(rs.getString(1)).thenReturn("  ＲＡＧ  ");
                return List.of(mapper.mapRow(rs,0));
            });
        var proposed=new PersonalMemoryService.AiCandidate(
            DECLARES_SKILL,"rag",null,null,Sensitivity.RESTRICTED,"synthetic-key-003");
        assertThatThrownBy(() -> memories.proposeAiCandidate(proposed))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void changedOriginOrSourceCannotReplayExistingRequestKey() {
        owner(7);
        var old=new PersonalMemoryService.Memory(21L,PERSON,"7",DECLARES_SKILL,
            LITERAL,null,"学习 RAG",USER_INPUT,null,"AI_CANDIDATE",
            "PENDING","RESTRICTED",null,null,null,LocalDateTime.now());
        var revised=new PersonalMemoryService.Proposed(PERSON,"7",DECLARES_SKILL,
            LITERAL,null,"学习 RAG",CHAT_MESSAGE,"91",null,null,
            Sensitivity.RESTRICTED,"synthetic-key-004");
        assertThatThrownBy(() -> PersonalMemoryService.matchingReplay(old,revised,null,"AI_CANDIDATE"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        verifyNoInteractions(db);
    }

    @Test void deletedChatInvalidatesLinkedEvidenceInDefaultContext() {
        owner(7);
        var linked=new PersonalMemoryService.Memory(30L,PERSON,"7",DECLARES_SKILL,
            LITERAL,null,"学习 RAG",CHAT_MESSAGE,"91","AI_CANDIDATE",
            "CONFIRMED","NORMAL",null,null,null,LocalDateTime.now());
        when(db.query(contains("AND sensitivity='NORMAL'"),
                any(RowMapper.class),eq(7L))).thenReturn(List.of(linked));
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwnedChatMessage("91");
        assertThat(memories.listCurrent()).isEmpty();
        verify(references).requireOwnedChatMessage("91");
    }
    @Test void readOnlyInspectionMarksEquivalentAndMaybeRelatedButNeverDeclaresAConflict() throws Exception {
        owner(7);
        when(db.query(contains("SELECT object_value,valid_from,valid_to"),
                any(RowMapper.class),eq(7L),eq("7"),eq("DECLARES_SKILL"),eq(0L)))
            .thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                RowMapper<Object> mapper=invocation.getArgument(1);
                ResultSet rs=mock(ResultSet.class);
                when(rs.getString(1)).thenReturn("我正在学习 RAG 入门");
                return List.of(mapper.mapRow(rs,0));
            });
        var related=new PersonalMemoryService.AiCandidate(
            DECLARES_SKILL,"学习 RAG",null,null,Sensitivity.RESTRICTED,"inspect-key-001");
        assertThat(memories.inspectAiCandidate(related).disposition())
            .isEqualTo("POSSIBLY_RELATED");
        var newFact=new PersonalMemoryService.AiCandidate(
            DECLARES_SKILL,"独立完成 Java 构建",null,null,Sensitivity.RESTRICTED,"inspect-key-002");
        assertThat(memories.inspectAiCandidate(newFact).disposition())
            .isEqualTo("NEW");
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void originalMessagePreviewIsOwnerOnlyAndRequiresExplicitSelectedAssertion() throws Exception {
        owner(7);
        var linked=new PersonalMemoryService.Memory(33L,PERSON,"7",DECLARES_SKILL,
            LITERAL,null,"学习 RAG",CHAT_MESSAGE,"91","AI_CANDIDATE",
            "PENDING","RESTRICTED",null,null,null,LocalDateTime.now());
        when(db.query(contains("WHERE id=? AND user_id=? LIMIT 1"),
            any(RowMapper.class),eq(33L),eq(7L))).thenReturn(List.of(linked));
        when(db.query(contains("SELECT m.content,m.created_at"),
            any(RowMapper.class),eq(91L),eq(7L))).thenAnswer(invocation -> {
                @SuppressWarnings("unchecked")
                RowMapper<Object> mapper=invocation.getArgument(1);
                ResultSet rs=mock(ResultSet.class);
                when(rs.getString(1)).thenReturn("我正在学习 RAG");
                when(rs.getTimestamp(2)).thenReturn(
                    java.sql.Timestamp.valueOf("2026-11-21 21:00:00"));
                return List.of(mapper.mapRow(rs,0));
            });
        var preview=memories.sourcePreview(33L);
        assertThat(preview.messageId()).isEqualTo(91L);
        assertThat(preview.messageText()).isEqualTo("我正在学习 RAG");
        verify(references).requireOwnedChatMessage("91");

        owner(8);
        assertThatThrownBy(() -> memories.sourcePreview(33L))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verify(db,never()).query(contains("SELECT m.content,m.created_at"),
            any(RowMapper.class),eq(91L),eq(8L));
    }

    @Test void explicitlyOpenedNormalHistoryKeepsManageabilityOfRevokedSources() {
        owner(7);
        var stale=new PersonalMemoryService.Memory(43L,PERSON,"7",DECLARES_SKILL,
            LITERAL,null,"学习 RAG",CHAT_MESSAGE,"91","AI_CANDIDATE",
            "CONFIRMED","NORMAL",null,null,null,LocalDateTime.now());
        when(db.query(contains("AND status IN ('CONFIRMED','SUPERSEDED','INVALID')"),
            any(RowMapper.class),eq(7L))).thenReturn(List.of(stale));
        assertThat(memories.listNormalHistory()).containsExactly(stale);
        // Explicit management does not re-verify/implicitly erase a revoked source.
        verifyNoInteractions(references);
        owner(8);
        assertThat(memories.listNormalHistory()).isEmpty();
    }

}
