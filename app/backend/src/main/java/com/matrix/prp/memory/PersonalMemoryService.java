package com.matrix.prp.memory;

import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.ontology.PersonalOntology.NodeType;
import com.matrix.prp.ontology.PersonalOntology.Relation;
import com.matrix.prp.ontology.PersonalOntology.Sensitivity;
import com.matrix.prp.ontology.PersonalOntologyAssertionGuard;
import com.matrix.prp.ontology.PersonalOntologyAssertionGuard.EvidenceSource;
import com.matrix.prp.ontology.PersonalOntologyReferenceGuard;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import java.sql.PreparedStatement;
import java.sql.Statement;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Owner-only, first-party memory workflow. All new facts start PENDING.
 *
 * Explicit UI confirmation is a separate REST action. Do not expose any of
 * these writes as unapproved MCP tools, and do not export raw memories to a
 * model without a separate authorization gate.
 */
@Service
@Profile("!test")
public class PersonalMemoryService {
    public record Proposed(NodeType subjectType, String subjectRef, Relation predicate,
                           NodeType objectType, String objectRef, String objectValue,
                           EvidenceSource sourceType, String sourceRef,
                           LocalDate validFrom, LocalDate validTo,
                           Sensitivity sensitivity, String requestKey) {}
    public record Memory(long id, NodeType subjectType, String subjectRef,
                         Relation predicate, NodeType objectType, String objectRef,
                         String objectValue, EvidenceSource sourceType, String sourceRef,
                         String origin, String status, String sensitivity,
                         LocalDate validFrom, LocalDate validTo, Long supersedesId,
                         LocalDateTime createdAt) {}

    private static final String COLS="id,subject_type,subject_ref,predicate,object_type,"
        + "object_ref,object_value,source_type,source_ref,origin,status,sensitivity,"
        + "valid_from,valid_to,supersedes_id,created_at";
    private static final RowMapper<Memory> MAPPER=(rs,n)->new Memory(
        rs.getLong("id"),NodeType.valueOf(rs.getString("subject_type")),
        rs.getString("subject_ref"),Relation.valueOf(rs.getString("predicate")),
        NodeType.valueOf(rs.getString("object_type")),rs.getString("object_ref"),
        rs.getString("object_value"),EvidenceSource.valueOf(rs.getString("source_type")),
        rs.getString("source_ref"),rs.getString("origin"),rs.getString("status"),
        rs.getString("sensitivity"),
        rs.getDate("valid_from")==null?null:rs.getDate("valid_from").toLocalDate(),
        rs.getDate("valid_to")==null?null:rs.getDate("valid_to").toLocalDate(),
        rs.getObject("supersedes_id")==null?null:rs.getLong("supersedes_id"),
        rs.getTimestamp("created_at").toLocalDateTime());

    private final JdbcTemplate db;
    private final PersonalOntologyAssertionGuard assertions;

    public PersonalMemoryService(JdbcTemplate db,PersonalOntologyReferenceGuard references) {
        this.db=db;
        this.assertions=new PersonalOntologyAssertionGuard(references);
    }

    /** Current, public-to-self NORMAL facts only. Never return unconfirmed/expired facts by default. */
    public List<Memory> listCurrent() {
        long owner=CurrentUser.id();
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions WHERE user_id=?"
            + " AND status='CONFIRMED' AND sensitivity='NORMAL'"
            + " AND (valid_from IS NULL OR valid_from<=CURRENT_DATE())"
            + " AND (valid_to IS NULL OR valid_to>=CURRENT_DATE())"
            + " ORDER BY id DESC LIMIT 100",MAPPER,owner).stream()
            .filter(this::validEvidence).toList();
    }

    /** Candidate queue is intentionally separate from retrieval for AI context. */
    public List<Memory> pending() {
        long owner=CurrentUser.id();
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions WHERE user_id=?"
            + " AND status='PENDING' ORDER BY id DESC LIMIT 100",MAPPER,owner).stream()
            .filter(this::validEvidence).toList();
    }

    public Memory get(long id) {
        positive(id);
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions"
            + " WHERE id=? AND user_id=? LIMIT 1",MAPPER,id,CurrentUser.id())
            .stream().findFirst().orElseThrow(PersonalMemoryService::notFound);
    }

    @Transactional
    public Memory propose(Proposed proposal) {
        return proposeWithParent(proposal,null);
    }

    @Transactional
    public Memory proposeReplacement(long oldId, Proposed proposal) {
        Memory previous=get(oldId);
        if (!"CONFIRMED".equals(previous.status())) throw conflict("Only confirmed facts can be replaced");
        return proposeWithParent(proposal,oldId);
    }

    private Memory proposeWithParent(Proposed p,Long supersedes) {
        validate(p);
        long owner=CurrentUser.id();
        if (!db.query("SELECT id FROM prp_personal_assertions"
            + " WHERE user_id=? AND request_key=? LIMIT 1",
            (rs,row)->rs.getLong(1),owner,p.requestKey()).isEmpty()) {
            throw conflict("Memory request key already used");
        }
        var keys=new GeneratedKeyHolder();
        var now=LocalDateTime.now();
        String origin=p.sourceType()==EvidenceSource.USER_INPUT?"USER_CONFIRMED":"BUSINESS_REFERENCE";
        Sensitivity sensitivity=effectiveSensitivity(p);
        db.update(con->{
            PreparedStatement ps=con.prepareStatement(
                "INSERT INTO prp_personal_assertions"
                + " (user_id,subject_type,subject_ref,predicate,object_type,object_ref,"
                + "object_value,source_type,source_ref,origin,status,sensitivity,"
                + "valid_from,valid_to,supersedes_id,request_key,created_at,updated_at)"
                + " VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?,?,?,?,?,?,?)",
                Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1,owner);
            ps.setString(2,p.subjectType().name());
            ps.setString(3,p.subjectRef());
            ps.setString(4,p.predicate().name());
            ps.setString(5,p.objectType().name());
            ps.setString(6,p.objectRef());
            ps.setString(7,p.objectValue());
            ps.setString(8,p.sourceType().name());
            ps.setString(9,p.sourceRef());
            ps.setString(10,origin);
            ps.setString(11,sensitivity.name());
            ps.setObject(12,p.validFrom());
            ps.setObject(13,p.validTo());
            if(supersedes==null)ps.setNull(14,java.sql.Types.BIGINT);
            else ps.setLong(14,supersedes);
            ps.setString(15,p.requestKey());
            ps.setObject(16,now);
            ps.setObject(17,now);
            return ps;
        },keys);
        Number key=keys.getKey();
        if(key==null)throw new IllegalStateException("No memory generated key");
        return get(key.longValue());
    }

    /** Confirmation re-checks both endpoints and the source; no inferred grants. */
    @Transactional
    public Memory confirm(long id) {
        Memory m=get(id);
        if("CONFIRMED".equals(m.status())) return m;
        if(!"PENDING".equals(m.status())) throw conflict("Memory is no longer pending");
        assertions.requireValid(toCandidate(m));
        long owner=CurrentUser.id();
        if(m.supersedesId()!=null) {
            // Lock predecessor in the same transaction; never overwrite a
            // previously replaced or invalidated assertion.
            List<String> old=db.query("SELECT status FROM prp_personal_assertions"
                + " WHERE id=? AND user_id=? FOR UPDATE",
                (rs,n)->rs.getString(1),m.supersedesId(),owner);
            if(old.size()!=1 || !"CONFIRMED".equals(old.get(0)))
                throw conflict("Predecessor is no longer current");
            if(db.update("UPDATE prp_personal_assertions SET status='SUPERSEDED',updated_at=?"
                + " WHERE id=? AND user_id=? AND status='CONFIRMED'",
                LocalDateTime.now(),m.supersedesId(),owner)!=1)
                throw conflict("Predecessor changed concurrently");
        }
        if(db.update("UPDATE prp_personal_assertions SET status='CONFIRMED',updated_at=?"
            + " WHERE id=? AND user_id=? AND status='PENDING'",
            LocalDateTime.now(),id,owner)!=1)
            throw conflict("Memory changed concurrently");
        return get(id);
    }

    @Transactional
    public Memory invalidate(long id) {
        Memory m=get(id);
        if("INVALID".equals(m.status())) return m;
        if("SUPERSEDED".equals(m.status())) throw conflict("Superseded fact cannot be reactivated");
        int count=db.update("UPDATE prp_personal_assertions SET status='INVALID',updated_at=?"
            + " WHERE id=? AND user_id=? AND status IN ('PENDING','CONFIRMED')",
            LocalDateTime.now(),id,CurrentUser.id());
        if(count!=1) throw conflict("Memory changed concurrently");
        return get(id);
    }

    /** Explicit user deletion, not a soft-deleted query-only tombstone. */
    @Transactional
    public void erase(long id) {
        get(id);
        long owner=CurrentUser.id();
        // FK restricts deletion of a superseded parent. Detach only this
        // owner's references; do not keep original sensitive values.
        db.update("UPDATE prp_personal_assertions SET supersedes_id=NULL,updated_at=?"
            + " WHERE user_id=? AND supersedes_id=?",LocalDateTime.now(),owner,id);
        if(db.update("DELETE FROM prp_personal_assertions WHERE id=? AND user_id=?",
            id,owner)!=1) throw conflict("Memory changed concurrently");
    }

    static Sensitivity effectiveSensitivity(Proposed proposed) {
        return proposed.sensitivity()==null ? Sensitivity.RESTRICTED : proposed.sensitivity();
    }

    private static PersonalOntologyAssertionGuard.Candidate toCandidate(Memory m) {
        return new PersonalOntologyAssertionGuard.Candidate(
            m.subjectType(),m.subjectRef(),m.predicate(),m.objectType(),
            m.objectRef(),m.objectValue(),m.sourceType(),m.sourceRef(),
            m.validFrom(),m.validTo());
    }
    private boolean validEvidence(Memory m) {
        try {
            assertions.requireValid(toCandidate(m));
            return true;
        }catch(ResponseStatusException | IllegalArgumentException invalidOrRevoked) {
            return false;
        }
    }
    private void validate(Proposed p) {
        if(p==null || p.requestKey()==null || !p.requestKey().matches("[a-zA-Z0-9_-]{8,80}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid memory request key");
        assertions.requireValid(new PersonalOntologyAssertionGuard.Candidate(
            p.subjectType(),p.subjectRef(),p.predicate(),p.objectType(),
            p.objectRef(),p.objectValue(),p.sourceType(),p.sourceRef(),
            p.validFrom(),p.validTo()));
    }
    private static void positive(long id) {
        if(id<=0)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid memory ID");
    }
    private static ResponseStatusException notFound() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND,"Memory not found");
    }
    private static ResponseStatusException conflict(String msg) {
        return new ResponseStatusException(HttpStatus.CONFLICT,msg);
    }
}
