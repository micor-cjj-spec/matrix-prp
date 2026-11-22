package com.matrix.prp.ontology;

import com.matrix.prp.ontology.PersonalOntology.NodeType;
import com.matrix.prp.ontology.PersonalOntology.Relation;
import java.time.LocalDate;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/**
 * Validates candidate Personal OS statements before any persistent write.
 *
 * <p>Domain services must separately enforce proposal confirmation, source
 * freshness, sensitive-data policy and authorization to export model context.
 * Validation here never grants permission to write or to invoke a model.
 */
public final class PersonalOntologyAssertionGuard {
    public enum EvidenceSource { USER_INPUT, RECORD, TASK, REVIEW }

    public record Candidate(
        NodeType subjectType, String subjectRef, Relation predicate,
        NodeType objectType, String objectRef, String objectValue,
        EvidenceSource sourceType, String sourceRef,
        LocalDate validFrom, LocalDate validTo
    ) { }

    private final PersonalOntologyReferenceGuard references;

    public PersonalOntologyAssertionGuard(PersonalOntologyReferenceGuard references) {
        this.references = Objects.requireNonNull(references);
    }

    public void requireValid(Candidate candidate) {
        if (candidate == null || candidate.subjectType() == null
                || candidate.predicate() == null || candidate.objectType() == null) {
            throw bad("Missing Personal OS statement type");
        }
        try {
            PersonalOntology.requireAllowed(
                candidate.subjectType(), candidate.predicate(), candidate.objectType());
        } catch (IllegalArgumentException ex) {
            throw bad("Unsupported Personal OS statement relationship");
        }
        if (candidate.validFrom() != null && candidate.validTo() != null
                && candidate.validFrom().isAfter(candidate.validTo())) {
            throw bad("Invalid Personal OS statement effective period");
        }

        // Both relationship endpoints are user-scoped. The source reference must
        // independently pass ownership checks, even if its ID equals an endpoint.
        references.requireOwned(candidate.subjectType(), candidate.subjectRef());

        if (candidate.objectType() == NodeType.LITERAL) {
            if (candidate.objectRef() != null
                    || candidate.objectValue() == null
                    || candidate.objectValue().isBlank()
                    || candidate.objectValue().length() > 512) {
                throw bad("Invalid literal value or object reference");
            }
        } else {
            if (candidate.objectValue() != null) {
                throw bad("Entity relationship must not contain literal text");
            }
            references.requireOwned(candidate.objectType(), candidate.objectRef());
        }

        if (candidate.sourceType() == null) {
            throw bad("Missing evidence source");
        }
        switch (candidate.sourceType()) {
            case USER_INPUT -> {
                if (candidate.sourceRef() != null) {
                    throw bad("Direct user evidence must not claim an external source");
                }
            }
            case RECORD -> references.requireOwned(NodeType.RECORD, candidate.sourceRef());
            case TASK -> references.requireOwned(NodeType.TASK, candidate.sourceRef());
            case REVIEW -> references.requireOwned(NodeType.REVIEW, candidate.sourceRef());
        }
    }

    private static ResponseStatusException bad(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
