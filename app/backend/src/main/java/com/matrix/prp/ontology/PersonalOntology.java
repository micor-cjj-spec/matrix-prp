package com.matrix.prp.ontology;

import java.util.Objects;

/**
 * First version of the PRP Personal OS vocabulary.
 *
 * <p>This class is only a semantic allowlist. It does not grant access to a
 * business record, establish identity, or persist a personal assertion.
 * Every reference must be resolved and ownership-checked by the calling service.
 */
public final class PersonalOntology {
    private PersonalOntology() {}

    public enum NodeType {
        PERSON, GOAL, SKILL, EVENT, RESOURCE, TASK, RECORD, REVIEW, LITERAL
    }

    public enum Relation {
        PURSUES(NodeType.PERSON, NodeType.GOAL),
        // P0 fallback: self-reported skills are user-confirmed literals,
        // not independently verified SKILL nodes.
        DECLARES_SKILL(NodeType.PERSON, NodeType.LITERAL),
        NEEDS_SKILL(NodeType.GOAL, NodeType.LITERAL),
        HAS_EVENT_RECORD(NodeType.PERSON, NodeType.RECORD),
        USES_RESOURCE_RECORD(NodeType.GOAL, NodeType.RECORD),
        // Reserved for verified entity IDs in a later phase.
        HAS_SKILL(NodeType.PERSON, NodeType.SKILL),
        REQUIRES(NodeType.GOAL, NodeType.SKILL),
        DEMONSTRATES(NodeType.EVENT, NodeType.SKILL),
        ADVANCES(NodeType.TASK, NodeType.GOAL),
        EVALUATES(NodeType.REVIEW, NodeType.GOAL),
        DOCUMENTS(NodeType.RECORD, NodeType.EVENT),
        SUPPORTS(NodeType.RESOURCE, NodeType.GOAL),
        CONSTRAINS(NodeType.RESOURCE, NodeType.TASK),
        PREFERS(NodeType.PERSON, NodeType.LITERAL),
        HAS_BACKGROUND(NodeType.PERSON, NodeType.LITERAL);

        private final NodeType subject;
        private final NodeType object;

        Relation(NodeType subject, NodeType object) {
            this.subject = subject;
            this.object = object;
        }

        public NodeType subjectType() { return subject; }
        public NodeType objectType() { return object; }
    }

    public enum AssertionStatus { PENDING, CONFIRMED, SUPERSEDED, INVALID }
    public enum Sensitivity { NORMAL, SENSITIVE, RESTRICTED }
    public enum Origin { USER_CONFIRMED, AI_CANDIDATE, BUSINESS_REFERENCE }
    public enum GoalStatus { PLANNED, ACTIVE, PAUSED, COMPLETED, CANCELLED }

    /** Validate semantic types only; authorization is a separate mandatory check. */
    public static void requireAllowed(NodeType subject, Relation relation, NodeType object) {
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(relation, "relation");
        Objects.requireNonNull(object, "object");
        if (subject == NodeType.LITERAL
                || subject != relation.subjectType()
                || object != relation.objectType()) {
            throw new IllegalArgumentException("Unsupported Personal OS assertion relation");
        }
    }
}
