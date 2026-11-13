package com.matrix.prp.ontology;

import static com.matrix.prp.ontology.PersonalOntology.NodeType.*;
import static com.matrix.prp.ontology.PersonalOntology.Relation.*;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PersonalOntologyTest {

    @Test
    void acceptsOnlyExplicitlyModelledRelations() {
        assertDoesNotThrow(() -> PersonalOntology.requireAllowed(PERSON, PURSUES, GOAL));
        assertDoesNotThrow(() -> PersonalOntology.requireAllowed(TASK, ADVANCES, GOAL));
        assertDoesNotThrow(() -> PersonalOntology.requireAllowed(REVIEW, EVALUATES, GOAL));
        assertDoesNotThrow(() -> PersonalOntology.requireAllowed(PERSON, PREFERS, LITERAL));
    }

    @Test
    void rejectsUnmodelledOrReversedLinks() {
        assertThrows(IllegalArgumentException.class,
            () -> PersonalOntology.requireAllowed(GOAL, PURSUES, PERSON));
        assertThrows(IllegalArgumentException.class,
            () -> PersonalOntology.requireAllowed(PERSON, ADVANCES, GOAL));
        assertThrows(IllegalArgumentException.class,
            () -> PersonalOntology.requireAllowed(GOAL, PREFERS, LITERAL));
        assertThrows(IllegalArgumentException.class,
            () -> PersonalOntology.requireAllowed(LITERAL, HAS_BACKGROUND, LITERAL));
    }

    @Test
    void rejectsNullRelationArguments() {
        assertThrows(NullPointerException.class,
            () -> PersonalOntology.requireAllowed(null, PURSUES, GOAL));
        assertThrows(NullPointerException.class,
            () -> PersonalOntology.requireAllowed(PERSON, null, GOAL));
        assertThrows(NullPointerException.class,
            () -> PersonalOntology.requireAllowed(PERSON, PURSUES, null));
    }
}
