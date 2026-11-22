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

    /**
     * Verifies a chat source belongs to the CURRENT owner, is a USER message,
     * and its conversation has not been deleted. No AI-supplied owner IDs.
     */
    public void requireOwnedChatMessage(String reference) {
        long owner=CurrentUser.id();
        long messageId=parseChatMessageId(reference);
        List<Integer> rows=jdbc.queryForList("""
            SELECT 1 FROM prp_ai_messages m
            JOIN prp_ai_conversations c ON c.id=m.conversation_id
            LEFT JOIN prp_ai_conversation_meta meta ON meta.conversation_id=c.id
            WHERE m.id=? AND c.user_id=? AND m.role='user'
              AND meta.deleted_at IS NULL LIMIT 1
            """,Integer.class,messageId,owner);
        if (rows.isEmpty()) throw notFound();
    }

    /**
     * A source quotation is checked against the actual persisted own message,
     * rather than believing the model's evidence text or a forged source ref.
     * Only the numeric message ID is stored in the assertion row.
     */
    public void requireOwnedChatQuote(String reference,String quote) {
        long owner=CurrentUser.id();
        long messageId=parseChatMessageId(reference);
        if (quote==null || quote.isBlank() || quote.length()>200
                || quote.chars().anyMatch(c -> Character.isISOControl(c) && c!='\n'
                    && c!='\r' && c!='\t')) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid conversation evidence quote");
        }
        List<String> messages=jdbc.queryForList("""
            SELECT m.content FROM prp_ai_messages m
            JOIN prp_ai_conversations c ON c.id=m.conversation_id
            LEFT JOIN prp_ai_conversation_meta meta ON meta.conversation_id=c.id
            WHERE m.id=? AND c.user_id=? AND m.role='user'
              AND meta.deleted_at IS NULL LIMIT 1
            """,String.class,messageId,owner);
        if (messages.isEmpty()) throw notFound();
        String text=messages.getFirst();
        if (text==null || !text.contains(quote))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Selected chat evidence is not present in the owned user message");
    }

    private static long parseChatMessageId(String reference) {
        if (reference==null || !reference.matches("[1-9][0-9]{0,18}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid chat source ID");
        try {
            long id=Long.parseLong(reference);
            if (id>0) return id;
        } catch (NumberFormatException ex) {
            // The regex may still match numbers beyond Long.MAX_VALUE.
        }
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid chat source ID");
    }

    private static ResponseStatusException notFound() {
        // Same response for missing and foreign-user entities.
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "Personal OS entity not found");
    }
}
