package com.matrix.prp.goals;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.ontology.PersonalOntology.GoalStatus;
import com.matrix.prp.ontology.PersonalOntology.NodeType;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * User-owned goals. Existing tasks/records remain the source of truth.
 * No direct AI tool writes, no task mutation, no implicit model access.
 */
@Service
@Profile("!test")
public final class GoalService {
    public record Goal(long id, String title, String description, String domain,
                       String status, String priority, String successCriteria,
                       LocalDate targetDate, LocalDateTime createdAt, LocalDateTime updatedAt) {}
    public record Create(String title, String description, String domain, String priority,
                         String successCriteria, LocalDate targetDate, String requestKey) {}
    public record Link(long assertionId, String predicate, String subjectType, String subjectRef,
                       String objectType, String objectRef, String objectValue) {}

    private static final String COLS = "id,title,description,domain,status,priority,"
        + "success_criteria,target_date,created_at,updated_at";
    private static final RowMapper<Goal> GOAL_MAPPER = (rs, row) ->
        new Goal(rs.getLong("id"), rs.getString("title"), rs.getString("description"),
            rs.getString("domain"), rs.getString("status"), rs.getString("priority"),
            rs.getString("success_criteria"),
            rs.getDate("target_date") == null ? null : rs.getDate("target_date").toLocalDate(),
            rs.getTimestamp("created_at").toLocalDateTime(),
            rs.getTimestamp("updated_at").toLocalDateTime());

    private final JdbcTemplate db;
    private final PersonalOntologyReferenceGuard references;

    public GoalService(JdbcTemplate db, PersonalOntologyReferenceGuard references) {
        this.db = db;
        this.references = references;
    }

    public List<Goal> list() {
        return db.query("SELECT " + COLS +
            " FROM prp_goals WHERE user_id=? AND deleted=0 ORDER BY created_at DESC LIMIT 100",
            GOAL_MAPPER, CurrentUser.id());
    }

    public Goal get(long id) {
        requirePositive(id);
        return db.query("SELECT " + COLS +
            " FROM prp_goals WHERE id=? AND user_id=? AND deleted=0 LIMIT 1",
            GOAL_MAPPER, id, CurrentUser.id()).stream().findFirst()
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Goal not found"));
    }

    @Transactional
    public Goal create(Create request) {
        validate(request);
        long owner = CurrentUser.id();
        List<Goal> existing = db.query("SELECT " + COLS +
                " FROM prp_goals WHERE user_id=? AND request_key=? AND deleted=0 LIMIT 1",
                GOAL_MAPPER, owner, request.requestKey());
        if (!existing.isEmpty()) return idempotent(existing.get(0), request);
        var keys = new GeneratedKeyHolder();
        var now = LocalDateTime.now();
        try {
            db.update(connection -> {
                PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO prp_goals (user_id,title,description,domain,status,priority,"
                    + "success_criteria,target_date,request_key,created_at,updated_at,deleted)"
                    + " VALUES (?,?,?,?,'PLANNED',?,?,?,?,?,?,0)", Statement.RETURN_GENERATED_KEYS);
                ps.setLong(1, owner);
                ps.setString(2, request.title().trim());
                ps.setString(3, request.description());
                ps.setString(4, request.domain());
                ps.setString(5, request.priority() == null ? "medium" : request.priority());
                ps.setString(6, request.successCriteria());
                ps.setDate(7, request.targetDate() == null ? null : Date.valueOf(request.targetDate()));
                ps.setString(8, request.requestKey());
                ps.setObject(9, now);
                ps.setObject(10, now);
                return ps;
            }, keys);
        } catch (DataIntegrityViolationException duplicate) {
            // Strictly scoped and payload-checked idempotency; never swallow
            // a foreign-key or unrelated database integrity failure.
            existing = db.query("SELECT " + COLS
                + " FROM prp_goals WHERE user_id=? AND request_key=? AND deleted=0 LIMIT 1",
                GOAL_MAPPER, owner, request.requestKey());
            if (!existing.isEmpty()) return idempotent(existing.get(0), request);
            throw duplicate;
        }
        Number key = keys.getKey();
        if (key == null) throw new IllegalStateException("No goal generated key");
        return get(key.longValue());
    }

    private static Goal idempotent(Goal prior, Create request) {
        if (!prior.title().equals(request.title().trim())
                || !Objects.equals(prior.description(), request.description())
                || !prior.domain().equals(request.domain())
                || !prior.priority().equals(request.priority() == null ? "medium" : request.priority())
                || !Objects.equals(prior.successCriteria(), request.successCriteria())
                || !Objects.equals(prior.targetDate(), request.targetDate())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Goal request key already used");
        }
        return prior;
    }

    @Transactional
    public Goal changeStatus(long id, String next) {
        Goal old = get(id);
        GoalStatus to = status(next);
        GoalStatus from = status(old.status());
        if (to == from) return old;
        if (!allowed(from, to)) throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Goal transition not permitted");
        int updated = db.update("UPDATE prp_goals SET status=?,updated_at=?"
            + " WHERE id=? AND user_id=? AND status=? AND deleted=0",
            to.name(), LocalDateTime.now(), id, CurrentUser.id(), from.name());
        if (updated != 1) throw new ResponseStatusException(HttpStatus.CONFLICT,
            "Goal changed concurrently");
        return get(id);
    }

    @Transactional
    public void delete(long id) {
        get(id);
        long owner = CurrentUser.id();
        int updated = db.update("UPDATE prp_goals SET deleted=1,updated_at=?"
            + " WHERE id=? AND user_id=? AND deleted=0",
            LocalDateTime.now(), id, owner);
        if (updated != 1) throw new ResponseStatusException(HttpStatus.CONFLICT,
            "Goal changed concurrently");
        // Invalidating relationships on the same transaction prevents stale
        // goal references from being treated as current confirmed facts.
        String ref = Long.toString(id);
        db.update("UPDATE prp_personal_assertions SET status='INVALID',updated_at=?"
            + " WHERE user_id=? AND status IN ('PENDING','CONFIRMED')"
            + " AND ((subject_type='GOAL' AND subject_ref=?)"
            + " OR (object_type='GOAL' AND object_ref=?))",
            LocalDateTime.now(), owner, ref, ref);
    }

    public List<Link> context(long id) {
        get(id);
        long owner = CurrentUser.id();
        String ref = Long.toString(id);
        String sql = "SELECT id,predicate,subject_type,subject_ref,"
            + "object_type,object_ref,object_value,source_type,source_ref"
            + " FROM prp_personal_assertions WHERE user_id=? AND status='CONFIRMED'"
            + " AND sensitivity='NORMAL' AND (valid_from IS NULL OR valid_from<=CURRENT_DATE())"
            + " AND (valid_to IS NULL OR valid_to>=CURRENT_DATE())"
            + " AND ((subject_type='GOAL' AND subject_ref=?)"
            + " OR (object_type='GOAL' AND object_ref=?)) ORDER BY id DESC LIMIT 100";
        return db.query(sql, (rs, row) -> {
            try {
                NodeType subj = NodeType.valueOf(rs.getString("subject_type"));
                NodeType obj = NodeType.valueOf(rs.getString("object_type"));
                references.requireOwned(subj, rs.getString("subject_ref"));
                if (obj != NodeType.LITERAL) references.requireOwned(obj, rs.getString("object_ref"));
                String source = rs.getString("source_type");
                String sourceRef = rs.getString("source_ref");
                if ("RECORD".equals(source)) references.requireOwned(NodeType.RECORD, sourceRef);
                else if ("TASK".equals(source)) references.requireOwned(NodeType.TASK, sourceRef);
                else if ("REVIEW".equals(source)) references.requireOwned(NodeType.REVIEW, sourceRef);
                else if (!"USER_INPUT".equals(source) || sourceRef != null) return null;
                return new Link(rs.getLong("id"), rs.getString("predicate"),
                    subj.name(), rs.getString("subject_ref"),
                    obj.name(), rs.getString("object_ref"), rs.getString("object_value"));
            } catch (IllegalArgumentException | ResponseStatusException badOrRevoked) {
                // Stale, foreign, revoked, or unknown evidence must not leak.
                return null;
            }
        }, owner, ref, ref).stream().filter(Objects::nonNull).toList();
    }

    private static GoalStatus status(String text) {
        try { return GoalStatus.valueOf(text); }
        catch (IllegalArgumentException | NullPointerException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown goal status");
        }
    }
    static boolean allowed(GoalStatus from, GoalStatus to) {
        return switch (from) {
            case PLANNED -> Set.of(GoalStatus.ACTIVE, GoalStatus.CANCELLED).contains(to);
            case ACTIVE -> Set.of(GoalStatus.PAUSED, GoalStatus.COMPLETED, GoalStatus.CANCELLED).contains(to);
            case PAUSED -> Set.of(GoalStatus.ACTIVE, GoalStatus.CANCELLED).contains(to);
            case COMPLETED, CANCELLED -> false;
        };
    }
    private static void requirePositive(long id) {
        if (id <= 0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid goal ID");
    }
    private static void validate(Create request) {
        if (request == null || request.title() == null || request.title().isBlank()
            || request.title().length() > 255
            || request.domain() == null || !request.domain().matches("[a-z][a-z0-9_-]{0,63}")
            || (request.priority() != null && !Set.of("low","medium","high").contains(request.priority()))
            || request.requestKey() == null || !request.requestKey().matches("[a-zA-Z0-9_-]{8,80}")
            || (request.description() != null && request.description().length() > 20000)
            || (request.successCriteria() != null && request.successCriteria().length() > 4000)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid goal input");
        }
    }
}
