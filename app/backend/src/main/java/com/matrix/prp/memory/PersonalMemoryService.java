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
import org.springframework.dao.DataIntegrityViolationException;
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

    /**
     * Model-suggested facts are not user-authored facts. This payload does not
     * accept a principal ID, entity reference, evidence claim or confirmation.
     */
    public record AiCandidate(Relation predicate, String value, LocalDate validFrom,
                              LocalDate validTo, Sensitivity sensitivity, String requestKey,
                              Long sourceMessageId, String evidenceQuote) {
        // Previous first-party synthetic candidate submissions stay unsourced.
        public AiCandidate(Relation predicate, String value, LocalDate validFrom,
                           LocalDate validTo, Sensitivity sensitivity, String requestKey) {
            this(predicate,value,validFrom,validTo,sensitivity,requestKey,null,null);
        }
    }

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
    private final PersonalOntologyReferenceGuard references;

    public PersonalMemoryService(JdbcTemplate db,PersonalOntologyReferenceGuard references) {
        this.db=db;
        this.references=references;
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

    /**
     * Authenticated, first-party-only management of sensitive/restricted facts.
     * Never call from an AI context builder or register as an MCP tool.
     * The UI must fetch this list only after an explicit owner action.
     */
    public List<Memory> listPrivate() {
        long owner = CurrentUser.id();
        // Owner management must retain visibility of stale evidence so the
        // owner can correct or erase it; only default AI-safe retrieval filters
        // source validity. Never expose this endpoint to MCP.
        // Include archived/invalidated private facts so the owner can
        // permanently erase values even after a revocation or replacement.
        // PENDING candidates remain in the separate review queue.
        return db.query("SELECT " + COLS + " FROM prp_personal_assertions WHERE user_id=?"
            + " AND status IN ('CONFIRMED','SUPERSEDED','INVALID')"
            + " AND sensitivity IN ('SENSITIVE','RESTRICTED')"
            + " ORDER BY id DESC LIMIT 100", MAPPER, owner);
    }

    /**
     * Explicit first-party owner management, never default AI context or MCP.
     * Include archived and source-revoked NORMAL facts so owners can correct or
     * erase their data after a linked chat has been deleted.
     */
    public List<Memory> listNormalHistory() {
        long owner=CurrentUser.id();
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions WHERE user_id=?"
            + " AND sensitivity='NORMAL'"
            + " AND status IN ('CONFIRMED','SUPERSEDED','INVALID')"
            + " ORDER BY id DESC LIMIT 100",MAPPER,owner);
    }

    /** Candidate queue is intentionally separate from retrieval for AI context. */
    public List<Memory> pending() {
        long owner=CurrentUser.id();
        // A revoked evidence source must not hide its pending candidate from
        // the owner: rejection and erasure remain available. Confirmation
        // independently validates current source ownership.
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions WHERE user_id=?"
            + " AND status='PENDING' ORDER BY id DESC LIMIT 100",MAPPER,owner);
    }

    public Memory get(long id) {
        positive(id);
        return db.query("SELECT "+COLS+" FROM prp_personal_assertions"
            + " WHERE id=? AND user_id=? LIMIT 1",MAPPER,id,CurrentUser.id())
            .stream().findFirst().orElseThrow(PersonalMemoryService::notFound);
    }

    /** Owner-initiated, first-party-only source preview; never for MCP or AI context. */
    public record ChatSource(long messageId, String messageText, LocalDateTime sentAt) {}

    public ChatSource sourcePreview(long assertionId) {
        Memory memory=get(assertionId); // owner-scoped even for pending/private
        if (memory.sourceType()!=EvidenceSource.CHAT_MESSAGE
                || memory.sourceRef()==null)
            throw notFound();
        references.requireOwnedChatMessage(memory.sourceRef());
        long messageId;
        try { messageId=Long.parseLong(memory.sourceRef()); }
        catch (NumberFormatException invalid) { throw notFound(); }
        long owner=CurrentUser.id();
        return db.query("""
            SELECT m.content,m.created_at FROM prp_ai_messages m
            JOIN prp_ai_conversations c ON c.id=m.conversation_id
            LEFT JOIN prp_ai_conversation_meta meta ON meta.conversation_id=c.id
            WHERE m.id=? AND c.user_id=? AND m.role='user'
              AND meta.deleted_at IS NULL LIMIT 1
            """,(rs,n)->new ChatSource(messageId,
                rs.getString(1).length()>2000 ? rs.getString(1).substring(0,2000) : rs.getString(1),
                rs.getTimestamp(2).toLocalDateTime()),messageId,owner)
            .stream().findFirst().orElseThrow(PersonalMemoryService::notFound);
    }

    @Transactional
    public Memory propose(Proposed proposal) {
        return proposeWithParent(proposal,null,null);
    }

    /**
     * T-008a: narrow AI candidate intake, NEVER a confirmation. The owner identity,
     * source type and relation endpoints are resolved server-side; nothing in the
     * AI payload may select a different owner or assert independent verification.
     */
    @Transactional
    public Memory proposeAiCandidate(AiCandidate suggestion) {
        Proposed validated=checkedAiProposal(suggestion);
        validate(validated);
        // Transaction-scoped owner row lock closes the cross-request-key
        // check-then-insert race among parallel Personal OS AI submissions.
        lockOwnerForKnowledgeMutation();
        return proposeWithParent(validated,null,"AI_CANDIDATE");
    }

    /** Read-only preflight; never sends prior private facts back to the caller. */
    public record AiInspection(String requestKey, String disposition) {}

    public AiInspection inspectAiCandidate(AiCandidate suggestion) {
        Proposed p=checkedAiProposal(suggestion);
        validate(p); // owner, relation and chat evidence must all still be current
        List<ComparableFact> existing=comparableFacts(CurrentUser.id(),p.subjectRef(),
            p.predicate(),0L,true);
        if (existing.size()>200) return new AiInspection(p.requestKey(),"REVIEW_REQUIRED");
        String value=normalizedLiteral(p.objectValue());
        boolean related=false;
        for (ComparableFact old:existing) {
            if (old.value()==null || !overlaps(p.validFrom(),p.validTo(),old.from(),old.to())
                    || !comparableSourceIsValid(old))
                continue;
            String prior=normalizedLiteral(old.value());
            if (value.equals(prior)) return new AiInspection(p.requestKey(),"DUPLICATE");
            // A containment hint is not evidence of a contradiction or supersession.
            String shorter=value.length()<=prior.length()?value:prior;
            String longer=value.length()>prior.length()?value:prior;
            if (shorter.length()>=5 && longer.contains(shorter)
                    && shorter.length()*2>=longer.length()) related=true;
        }
        return new AiInspection(p.requestKey(),related?"POSSIBLY_RELATED":"NEW");
    }

    private Proposed checkedAiProposal(AiCandidate suggestion) {
        long owner=CurrentUser.id();
        if (suggestion==null || suggestion.predicate()==null ||
                !Set.of(Relation.DECLARES_SKILL,Relation.PREFERS,Relation.HAS_BACKGROUND)
                    .contains(suggestion.predicate()) ||
                suggestion.value()==null || suggestion.value().isBlank() ||
                suggestion.value().length()>256 ||
                suggestion.value().chars().anyMatch(Character::isISOControl)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "AI candidate must be a bounded self-reported skill, preference or background");
        }
        boolean hasId=suggestion.sourceMessageId()!=null;
        boolean hasQuote=suggestion.evidenceQuote()!=null;
        if (hasId!=hasQuote)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Chat evidence must include both a message ID and exact quotation");
        String sourceRef=null;
        EvidenceSource sourceType=EvidenceSource.USER_INPUT;
        if (hasId) {
            if (suggestion.sourceMessageId()<=0)
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Invalid chat source ID");
            sourceRef=Long.toString(suggestion.sourceMessageId());
            references.requireOwnedChatQuote(sourceRef,suggestion.evidenceQuote());
            sourceType=EvidenceSource.CHAT_MESSAGE;
        }
        return new Proposed(NodeType.PERSON,Long.toString(owner),
            suggestion.predicate(),NodeType.LITERAL,null,suggestion.value().strip(),
            sourceType,sourceRef,suggestion.validFrom(),suggestion.validTo(),
            suggestion.sensitivity(),suggestion.requestKey());
    }

    @Transactional
    public Memory proposeReplacement(long oldId, Proposed proposal) {
        Memory previous=get(oldId);
        if (!"CONFIRMED".equals(previous.status())) throw conflict("Only confirmed facts can be replaced");
        if (proposal == null || previous.subjectType() != proposal.subjectType()
                || !Objects.equals(previous.subjectRef(),proposal.subjectRef())
                || previous.predicate() != proposal.predicate()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Memory replacement must describe the same subject and predicate");
        }
        return proposeWithParent(proposal,oldId,null);
    }

    private Memory proposeWithParent(Proposed p,Long supersedes,String forcedOrigin) {
        validate(p);
        String origin=forcedOrigin!=null?forcedOrigin:
            p.sourceType()==EvidenceSource.USER_INPUT?"USER_CONFIRMED":"BUSINESS_REFERENCE";
        long owner=CurrentUser.id();
        List<Long> priorIds = db.query("SELECT id FROM prp_personal_assertions"
            + " WHERE user_id=? AND request_key=? LIMIT 1",
            (rs,row)->rs.getLong(1),owner,p.requestKey());
        if (!priorIds.isEmpty()) return matchingReplay(get(priorIds.get(0)),p,supersedes,origin);
        // Avoid obvious duplicates before any AI-suggested memory can be queued.
        if ("AI_CANDIDATE".equals(origin))
            requireNoExactDuplicate(owner,p.subjectRef(),p.predicate(),p.objectValue(),
                p.validFrom(),p.validTo(),0L,true);
        var keys=new GeneratedKeyHolder();
        var now=LocalDateTime.now();
        Sensitivity sensitivity=effectiveSensitivity(p);
        try {
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
        } catch (DataIntegrityViolationException race) {
            // Two simultaneous retries may pass the initial SELECT. The
            // unique (user_id,request_key) constraint is final authority.
            List<Long> ids = db.query("SELECT id FROM prp_personal_assertions"
                + " WHERE user_id=? AND request_key=? LIMIT 1",
                (rs,row)->rs.getLong(1),owner,p.requestKey());
            if (!ids.isEmpty()) return matchingReplay(get(ids.get(0)),p,supersedes,origin);
            throw race;
        }
        Number key=keys.getKey();
        if(key==null)throw new IllegalStateException("No memory generated key");
        return get(key.longValue());
    }

    static Memory matchingReplay(Memory prior, Proposed proposal, Long supersedes, String origin) {
        if (!Objects.equals(prior.origin(),origin)
                || prior.subjectType()!=proposal.subjectType()
                || !Objects.equals(prior.subjectRef(),proposal.subjectRef())
                || prior.predicate()!=proposal.predicate()
                || prior.objectType()!=proposal.objectType()
                || !Objects.equals(prior.objectRef(),proposal.objectRef())
                || !Objects.equals(prior.objectValue(),proposal.objectValue())
                || prior.sourceType()!=proposal.sourceType()
                || !Objects.equals(prior.sourceRef(),proposal.sourceRef())
                || !Objects.equals(prior.validFrom(),proposal.validFrom())
                || !Objects.equals(prior.validTo(),proposal.validTo())
                || !Objects.equals(prior.sensitivity(),effectiveSensitivity(proposal).name())
                || !Objects.equals(prior.supersedesId(),supersedes)) {
            throw conflict("Memory request key already used for another payload");
        }
        return prior;
    }

    /** Confirmation re-checks both endpoints and the source; no inferred grants. */
    @Transactional
    public Memory confirm(long id) {
        positive(id);
        // Before ANY consistent-read SELECT: otherwise REPEATABLE READ can
        // retain a stale snapshot from before waiting for the owner lock.
        lockOwnerForKnowledgeMutation();
        Memory m=get(id);
        if("CONFIRMED".equals(m.status())) return m;
        if(!"PENDING".equals(m.status())) throw conflict("Memory is no longer pending");
        assertions.requireValid(toCandidate(m));
        // A previously safe AI suggestion can become a duplicate while awaiting review.
        if ("AI_CANDIDATE".equals(m.origin()))
            requireNoExactDuplicate(CurrentUser.id(),m.subjectRef(),m.predicate(),m.objectValue(),
                m.validFrom(),m.validTo(),m.id(),false);
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

    /** Exact normalized duplicates only; different statements are not called conflicts. */
    private record ComparableFact(String value, LocalDate from, LocalDate to,
                                  String sourceType, String sourceRef) {}
    private static String normalizedLiteral(String value) {
        return java.text.Normalizer.normalize(value.strip(),java.text.Normalizer.Form.NFKC)
            .replaceAll("\\s+"," ").toLowerCase(java.util.Locale.ROOT);
    }
    private static boolean overlaps(LocalDate from,LocalDate to,LocalDate otherFrom,LocalDate otherTo) {
        return (to==null || otherFrom==null || !to.isBefore(otherFrom))
            && (otherTo==null || from==null || !otherTo.isBefore(from));
    }

    private List<ComparableFact> comparableFacts(long owner,String subjectRef,Relation predicate,
            long excludeId,boolean includePending) {
        String statuses=includePending ? "IN ('CONFIRMED','PENDING')" : "='CONFIRMED'";
        // Only these server-owned, hardcoded status fragments enter the SQL.
        String sql="SELECT object_value,valid_from,valid_to,source_type,source_ref FROM prp_personal_assertions"
            + " WHERE user_id=? AND subject_type='PERSON' AND subject_ref=?"
            + " AND predicate=? AND object_type='LITERAL' AND status "+statuses
            + " AND id<>? ORDER BY id DESC LIMIT 201";
        return db.query(sql,(rs,n)->new ComparableFact(rs.getString(1),
                rs.getDate(2)==null?null:rs.getDate(2).toLocalDate(),
                rs.getDate(3)==null?null:rs.getDate(3).toLocalDate(),
                rs.getString(4),rs.getString(5)),
            owner,subjectRef,predicate.name(),excludeId);
    }

    /**
     * Invalidated source references cannot make a dead assertion block a
     * newly verified statement. Existing owner history retains that row.
     */
    private boolean comparableSourceIsValid(ComparableFact fact) {
        try {
            if (fact.sourceType()==null) return false;
            if ("USER_INPUT".equals(fact.sourceType()))
                return fact.sourceRef()==null;
            switch (EvidenceSource.valueOf(fact.sourceType())) {
                case CHAT_MESSAGE -> references.requireOwnedChatMessage(fact.sourceRef());
                case RECORD -> references.requireOwned(NodeType.RECORD,fact.sourceRef());
                case TASK -> references.requireOwned(NodeType.TASK,fact.sourceRef());
                case REVIEW -> references.requireOwned(NodeType.REVIEW,fact.sourceRef());
                case USER_INPUT -> { }
            }
            return true;
        } catch (ResponseStatusException | IllegalArgumentException revoked) {
            return false;
        }
    }

    private void requireNoExactDuplicate(long owner,String subjectRef,Relation predicate,
            String literal,LocalDate from,LocalDate to,long excludeId,boolean includePending) {
        if (literal==null) return;
        List<ComparableFact> existing=comparableFacts(owner,subjectRef,predicate,
            excludeId,includePending);
        if (existing.size()>200)
            throw conflict("Too many facts to verify duplicates safely; review existing memories");
        String normalized=normalizedLiteral(literal);
        if (existing.stream().anyMatch(old->old.value()!=null
            && normalized.equals(normalizedLiteral(old.value()))
            && overlaps(from,to,old.from(),old.to())
            && comparableSourceIsValid(old))) {
            throw conflict("Equivalent knowledge is already pending or confirmed");
        }
    }

    static Sensitivity effectiveSensitivity(Proposed proposed) {
        return proposed.sensitivity()==null ? Sensitivity.RESTRICTED : proposed.sensitivity();
    }

    /**
     * Reuses the existing PRP user row as the narrowest shared InnoDB mutex.
     * Must be called from public @Transactional entrypoints ONLY. The lock is
     * released by the DB on commit/rollback; never use GET_LOCK on pooled sessions.
     */
    private void lockOwnerForKnowledgeMutation() {
        long owner=CurrentUser.id();
        Long locked=db.queryForObject(
            "SELECT id FROM prp_users WHERE id=? FOR UPDATE",Long.class,owner);
        if (locked==null || locked.longValue()!=owner)
            throw conflict("Personal knowledge owner is no longer available");
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
