package com.matrix.prp.memory;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT;
import com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

class PersonalMemoryServiceTests {
    private final JdbcTemplate db=mock(JdbcTemplate.class);
    private final PersonalOntologyReferenceGuard references=mock(PersonalOntologyReferenceGuard.class);
    private final PersonalMemoryService service=new PersonalMemoryService(db,references);

    private void user(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }

    @Test void directConfirmationCannotSkipCandidateValidation() {
        user(7);
        var invalid=new PersonalMemoryService.Proposed(
            PERSON,"7",HAS_BACKGROUND,LITERAL,null,"  ",USER_INPUT,null,
            null,null,null,"memory_req_0001");
        assertThatThrownBy(()->service.propose(invalid))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST));
        verifyNoInteractions(db);
    }

    @Test void crossUserEvidenceAndEndpointsUseReferenceGuardBeforeDatabaseWrite() {
        user(7);
        var proposed=new PersonalMemoryService.Proposed(
            PERSON,"7",HAS_EVENT_RECORD,RECORD,"99",null,EvidenceSource.RECORD,"99",
            null,null,null,"memory_req_0002");
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwned(RECORD,"99");
        assertThatThrownBy(()->service.propose(proposed))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verifyNoInteractions(db);
    }

    @Test void sensitiveOwnerListIsSeparateFromDefaultMemoryContext() {
        user(7);
        assertThat(service.listPrivate()).isEmpty();
        verify(db).query(contains("status IN ('CONFIRMED','SUPERSEDED','INVALID')"),
            any(org.springframework.jdbc.core.RowMapper.class), eq(7L));
        verifyNoInteractions(references);
    }

    @Test void anonymousCannotReadCandidateQueue() {
        assertThatThrownBy(service::pending)
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED));
        verifyNoInteractions(db);
    }

    @Test void unclassifiedMemoriesFailClosedToRestrictedVisibility() {
        var unspecified = new PersonalMemoryService.Proposed(
            PERSON,"7",DECLARES_SKILL,LITERAL,null,"Java",USER_INPUT,null,
            null,null,null,"memory_req_0003");
        assertThat(PersonalMemoryService.effectiveSensitivity(unspecified))
            .isEqualTo(com.matrix.prp.ontology.PersonalOntology.Sensitivity.RESTRICTED);
        var explicit = new PersonalMemoryService.Proposed(
            PERSON,"7",DECLARES_SKILL,LITERAL,null,"Java",USER_INPUT,null,
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "memory_req_0004");
        assertThat(PersonalMemoryService.effectiveSensitivity(explicit))
            .isEqualTo(com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL);
    }

    @Test void foreignOrRevokedTaskCannotBeLinkedToOwnGoal() {
        user(7);
        var edge=new PersonalMemoryService.Proposed(
            TASK,"99",ADVANCES,GOAL,"31",null,EvidenceSource.TASK,"99",
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "link_req_foreign01");
        when(db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,7L))
            .thenReturn(7L);
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwned(TASK,"99");
        assertThatThrownBy(()->service.propose(edge))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void sameTaskGoalEdgeRecoversPendingCandidateAcrossDifferentKeys() {
        user(7);
        var edge=new PersonalMemoryService.Proposed(
            TASK,"91",ADVANCES,GOAL,"31",null,EvidenceSource.TASK,"91",
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "link_req_0000001");
        when(db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,7L))
            .thenReturn(7L);
        when(db.query(
            contains("WHERE user_id=? AND request_key=? LIMIT 1"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(7L),eq("link_req_0000001"))).thenReturn(List.of());
        when(db.query(
            contains("AND predicate=? AND object_type='GOAL'"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(7L),eq("TASK"),eq("91"),eq("ADVANCES"),eq("31")))
            .thenReturn(List.of(55L));
        var prior=new PersonalMemoryService.Memory(
            55L,TASK,"91",ADVANCES,GOAL,"31",null,
            EvidenceSource.TASK,"91","BUSINESS_REFERENCE","PENDING","NORMAL",
            null,null,null,java.time.LocalDateTime.of(2026,11,22,1,0));
        when(db.query(
            contains("WHERE id=? AND user_id=? LIMIT 1"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(55L),eq(7L))).thenReturn(List.of(prior));

        var recovered=service.propose(edge);
        assertThat(recovered.id()).isEqualTo(55L);
        assertThat(recovered.status()).isEqualTo("PENDING");
        verify(references,atLeastOnce()).requireOwned(TASK,"91");
        verify(references).requireOwned(GOAL,"31");
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void foreignOrDeletedReviewCannotBeLinkedToOwnGoal() {
        user(7);
        var edge=new PersonalMemoryService.Proposed(
            REVIEW,"88",EVALUATES,GOAL,"31",null,EvidenceSource.REVIEW,"88",
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "review_link_foreign_01");
        when(db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,7L))
            .thenReturn(7L);
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwned(REVIEW,"88");
        assertThatThrownBy(()->service.propose(edge))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void sameReviewGoalEdgeRecoversConfirmedRelationAcrossDifferentKeys() {
        user(7);
        var edge=new PersonalMemoryService.Proposed(
            REVIEW,"42",EVALUATES,GOAL,"31",null,EvidenceSource.REVIEW,"42",
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "review_link_req_01");
        when(db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,7L))
            .thenReturn(7L);
        when(db.query(
            contains("WHERE user_id=? AND request_key=? LIMIT 1"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(7L),eq("review_link_req_01"))).thenReturn(List.of());
        when(db.query(
            contains("AND predicate=? AND object_type='GOAL'"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(7L),eq("REVIEW"),eq("42"),eq("EVALUATES"),eq("31")))
            .thenReturn(List.of(75L));
        var prior=new PersonalMemoryService.Memory(
            75L,REVIEW,"42",EVALUATES,GOAL,"31",null,
            EvidenceSource.REVIEW,"42","BUSINESS_REFERENCE","CONFIRMED","NORMAL",
            null,null,null,java.time.LocalDateTime.of(2026,11,22,1,0));
        when(db.query(
            contains("WHERE id=? AND user_id=? LIMIT 1"),
            any(org.springframework.jdbc.core.RowMapper.class),
            eq(75L),eq(7L))).thenReturn(List.of(prior));
        var recovered=service.propose(edge);
        assertThat(recovered.id()).isEqualTo(75L);
        assertThat(recovered.status()).isEqualTo("CONFIRMED");
        verify(references,atLeastOnce()).requireOwned(REVIEW,"42");
        verify(references).requireOwned(GOAL,"31");
        verify(db,never()).update(any(org.springframework.jdbc.core.PreparedStatementCreator.class),
            any(org.springframework.jdbc.support.KeyHolder.class));
    }

    @Test void recoveredGoalEdgeCannotReuseModifiedEvidenceOrSensitivity() {
        var prior=new PersonalMemoryService.Memory(
            55L,TASK,"91",ADVANCES,GOAL,"31",null,
            EvidenceSource.TASK,"91","BUSINESS_REFERENCE","PENDING","NORMAL",
            null,null,null,java.time.LocalDateTime.of(2026,11,22,1,0));
        var forged=new PersonalMemoryService.Proposed(
            TASK,"91",ADVANCES,GOAL,"31",null,EvidenceSource.USER_INPUT,null,
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.NORMAL,
            "different_source_01");
        assertThatThrownBy(()->PersonalMemoryService.matchingReplay(
            prior,forged,null,"USER_CONFIRMED"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        var reclassified=new PersonalMemoryService.Proposed(
            TASK,"91",ADVANCES,GOAL,"31",null,EvidenceSource.TASK,"91",
            null,null,com.matrix.prp.ontology.PersonalOntology.Sensitivity.RESTRICTED,
            "changed_sensitivity_01");
        assertThatThrownBy(()->PersonalMemoryService.matchingReplay(
            prior,reclassified,null,"BUSINESS_REFERENCE"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
    }

    @Test void missingOrNegativeIdRejectedWithoutDatabaseAccess() {
        user(7);
        assertThatThrownBy(()->service.confirm(0))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e->assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(()->service.erase(-1))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(db);
    }
}
