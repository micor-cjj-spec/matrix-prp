package com.matrix.prp.ontology;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource.USER_INPUT;
import com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class PersonalOntologyAssertionGuardTest {
    private final PersonalOntologyReferenceGuard references =
        mock(PersonalOntologyReferenceGuard.class);
    private final PersonalOntologyAssertionGuard guard =
        new PersonalOntologyAssertionGuard(references);

    private static PersonalOntologyAssertionGuard.Candidate literal(
            String sourceRef, PersonalOntologyAssertionGuard.EvidenceSource sourceType) {
        return new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", HAS_BACKGROUND, LITERAL, null,
            "Confirmed personal background", sourceType, sourceRef,
            LocalDate.parse("2026-11-01"), null);
    }

    @Test
    void checksSubjectAndOwnedEvidenceForLiteralFacts() {
        guard.requireValid(literal("19", EvidenceSource.RECORD));
        verify(references).requireOwned(PERSON, "7");
        verify(references).requireOwned(RECORD, "19");
        verifyNoMoreInteractions(references);
    }

    @Test
    void acceptsDirectUserSuppliedLiteralWithoutInventingDocumentProvenance() {
        guard.requireValid(literal(null, USER_INPUT));
        verify(references).requireOwned(PERSON, "7");
        verifyNoMoreInteractions(references);
    }

    @Test
    void validatesBothEndpointsAndSeparateEvidenceForEntityRelations() {
        var item = new PersonalOntologyAssertionGuard.Candidate(
            TASK, "4", ADVANCES, GOAL, "6", null, EvidenceSource.TASK, "4", null, null);
        guard.requireValid(item);
        verify(references).requireOwned(TASK, "4");
        verify(references).requireOwned(GOAL, "6");
        // Even when source is the same object, recheck its type and owner.
        verify(references, times(2)).requireOwned(TASK, "4");
        verifyNoMoreInteractions(references);
    }

    @Test
    void p0SkillLabelsRemainProvenancedLiterals() {
        guard.requireValid(new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", DECLARES_SKILL, LITERAL, null, "Java",
            USER_INPUT, null, null, null));
        guard.requireValid(new PersonalOntologyAssertionGuard.Candidate(
            GOAL, "6", NEEDS_SKILL, LITERAL, null, "Python",
            USER_INPUT, null, null, null));
        verify(references).requireOwned(PERSON, "7");
        verify(references).requireOwned(GOAL, "6");
        verifyNoMoreInteractions(references);
    }

    @Test
    void p0LifeEventMustBeAnOwnedExistingRecord() {
        guard.requireValid(new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", HAS_EVENT_RECORD, RECORD, "19", null,
            EvidenceSource.RECORD, "19", null, null));
        verify(references).requireOwned(PERSON, "7");
        verify(references, times(2)).requireOwned(RECORD, "19");
        verifyNoMoreInteractions(references);
    }

    @Test
    void rejectsWrongSemanticTypesBeforeAccessingRecords() {
        var wrong = new PersonalOntologyAssertionGuard.Candidate(
            GOAL, "6", PURSUES, PERSON, "7", null, USER_INPUT, null, null, null);
        assertBad(wrong);
        verifyNoInteractions(references);
    }

    @Test
    void rejectsInvalidDateRangesBeforeAccessingRecords() {
        var invalid = new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", HAS_BACKGROUND, LITERAL, null,
            "valid", USER_INPUT, null, LocalDate.parse("2026-11-02"),
            LocalDate.parse("2026-11-01"));
        assertBad(invalid);
        verifyNoInteractions(references);
    }

    @Test
    void blocksMalformedLiteralsAndClaimedUserInputSources() {
        assertBad(new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", HAS_BACKGROUND, LITERAL, "8",
            "not-a-pure-literal", USER_INPUT, null, null, null));
        assertBad(new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", HAS_BACKGROUND, LITERAL, null,
            "   ", USER_INPUT, null, null, null));
        assertBad(new PersonalOntologyAssertionGuard.Candidate(
            PERSON, "7", PREFERS, LITERAL, null,
            "v".repeat(513), USER_INPUT, null, null, null));
        assertBad(literal("spoofed-record-15", USER_INPUT));
        assertBad(literal(null, null));
    }

    @Test
    void blocksLiteralTextInEntityReferences() {
        var invalid = new PersonalOntologyAssertionGuard.Candidate(
            TASK, "4", ADVANCES, GOAL, "6", "smuggled text", USER_INPUT,
            null, null, null);
        assertBad(invalid);
    }

    @Test
    void propagatesReferenceOwnershipRejectionWithoutConcealingIt() {
        doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
            .when(references).requireOwned(RECORD, "19");
        assertThatThrownBy(() -> guard.requireValid(literal("19", EvidenceSource.RECORD)))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(error ->
                org.assertj.core.api.Assertions.assertThat(
                    ((ResponseStatusException) error).getStatusCode())
                    .isEqualTo(HttpStatus.NOT_FOUND));
    }

    private void assertBad(PersonalOntologyAssertionGuard.Candidate value) {
        assertThatThrownBy(() -> guard.requireValid(value))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(error ->
                org.assertj.core.api.Assertions.assertThat(
                    ((ResponseStatusException) error).getStatusCode())
                    .isEqualTo(HttpStatus.BAD_REQUEST));
    }
}
