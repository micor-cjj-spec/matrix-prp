package com.matrix.prp.ontology;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.ontology.PersonalOntology.NodeType;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/**
 * Reference validation boundary for persisted Personal OS assertions.
 * Database ownership is checked independently from semantic type validation.
 * The model never supplies a user ID, table name, or SQL expression.
 */
@Component
@Profile("!test")
public final class PersonalOntologyReferenceGuard {
    private final JdbcTemplate jdbc;

    public PersonalOntologyReferenceGuard(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void requireOwned(NodeType type, String reference) {
        long owner = CurrentUser.id();
        if (type == null || reference == null || !reference.matches("[1-9][0-9]{0,18}")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid Personal OS entity reference");
        }
        final long id;
        try {
            id = Long.parseLong(reference);
        } catch (NumberFormatException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid Personal OS entity reference");
        }
        if (type == NodeType.PERSON) {
            if (id != owner) throw notFound();
            return;
        }
        String sql = switch (type) {
            case GOAL -> "SELECT 1 FROM prp_goals WHERE id=? AND user_id=? AND deleted=0 LIMIT 1";
            case TASK -> "SELECT 1 FROM prp_tasks WHERE id=? AND user_id=? AND deleted=0 LIMIT 1";
            case RECORD -> "SELECT 1 FROM prp_records WHERE id=? AND user_id=? AND deleted=0 LIMIT 1";
            case REVIEW -> "SELECT 1 FROM prp_reviews WHERE id=? AND user_id=? AND deleted=0 LIMIT 1";
            // These nodes have no validated persistent source in V0.5.
            // They must not be constructed from arbitrary strings supplied by AI.
            case SKILL, EVENT, RESOURCE, LITERAL, PERSON ->
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Entity type has no verified resolver");
        };
        List<Integer> rows = jdbc.queryForList(sql, Integer.class, id, owner);
        if (rows.isEmpty()) throw notFound();
    }

    private static ResponseStatusException notFound() {
        // Same response for missing and foreign-user entities.
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "Personal OS entity not found");
    }
}
