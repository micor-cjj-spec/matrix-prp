package com.matrix.prp.mcp;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validator;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Owner-scoped MCP drafts. The model only proposes a bounded business request.
 * A separate, explicit confirmation consumes a row once under a DB lock.
 * Never accept a userId, SQL statement or URL supplied by a model.
 */
@Service
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpDraftService {
    public enum Kind { TASK, FINANCE, RECORD, TASK_UPDATE, TASK_DELETE, WELLNESS_CREATE, WELLNESS_UPDATE, WELLNESS_DELETE }
    public record TaskChange(long taskId, com.matrix.prp.tasks.model.TaskItem before,
                             String revision, CreateTaskRequest after, String status) {}
    public record Preview(String draftId, String kind, JsonNode values, String expiresAt,
                          String instruction) {}
    public record Result(String draftId, String kind, JsonNode saved, boolean alreadySaved) {}
    public record Review(String draftId, String kind, JsonNode values, String status, String expiresAt) {}
    public record Approval(String status, int remainingAttempts) {}
    private record Stored(String kind, String payload, String result, String status,
                          LocalDateTime expiresAt) {}

    private McpWellnessSupport wellnessSupport;
    @org.springframework.beans.factory.annotation.Autowired
    void configureWellnessSupport(McpWellnessSupport support) { this.wellnessSupport=support; }
    private McpWellnessSupport health() {
        if (wellnessSupport==null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Wellness tools unavailable");
        return wellnessSupport;
    }
    @Transactional
    public Preview prepareWellness(String entity, long id, McpWellnessSupport.Input input, Kind kind) {
        requireWrite();
        if (kind!=Kind.WELLNESS_CREATE && kind!=Kind.WELLNESS_UPDATE && kind!=Kind.WELLNESS_DELETE)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid health operation");
        if (kind==Kind.WELLNESS_CREATE ? id!=0 : id<=0)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid health target");
        return prepare(kind, health().capture(entity,id,input,kind==Kind.WELLNESS_DELETE));
    }
    /**
     * Tool argument object is a flexible JSON map to avoid SDK-generated
     * required fields for mutually exclusive wellness alternatives. Recreate
     * the validated domain input before preparing the immutable draft.
     */
    @Transactional
    public Preview prepareWellnessFromMcp(String entity, long id, java.util.Map<String, Object> raw, Kind kind) {
        if (kind != Kind.WELLNESS_CREATE && kind != Kind.WELLNESS_UPDATE)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid wellness operation");
        return prepareWellness(entity, id, health().fromMcpInput(entity, raw), kind);
    }

    static String operationScope(String kind) {
        return switch (Kind.valueOf(kind)) {
            case TASK_UPDATE -> "prp.write.update";
            case TASK_DELETE -> "prp.write.delete";
            case WELLNESS_CREATE -> "prp.wellness.write.create";
            case WELLNESS_UPDATE -> "prp.wellness.write.update";
            case WELLNESS_DELETE -> "prp.wellness.write.delete";
            default -> "prp.write.create";
        };
    }

    private final JdbcTemplate db;
    private final ObjectMapper json;
    private final Validator validator;
    private final TaskService tasks;
    private final FinanceService finance;
    private final RecordService records;
    private final boolean writeEnabled;
    private final String approvalBase;
    private final UserStore users;
    private final PasswordEncoder passwords;

    // Default OFF: app-only, human-click approval flow, never a model-controlled shortcut.
    @Value("${matrix-prp.mcp.chatgpt-health-approval-ui-enabled:false}")
    private boolean chatgptApprovalUiEnabled;

    public McpDraftService(JdbcTemplate db, ObjectMapper json, Validator validator,
                           TaskService tasks, FinanceService finance, RecordService records,
                           UserStore users, PasswordEncoder passwords,
                           @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled,
                           @Value("${matrix-prp.mcp.oauth.resource:}") String resource) {
        this.db = db;
        this.json = json;
        this.validator = validator;
        this.tasks = tasks;
        this.finance = finance;
        this.records = records;
        this.writeEnabled = writeEnabled;
        this.approvalBase = approvalBase(resource);
        this.users = users;
        this.passwords = passwords;
    }

    static String approvalBase(String resource) {
        if (resource == null || resource.isBlank()) return "/prp/";
        var uri = java.net.URI.create(McpOAuthResourceServerConfig.strictHttps(resource, "MCP approval origin"));
        return uri.resolve("/prp/").toString();
    }

    private void requireWrite() {
        CurrentUser.id(); // Fail closed if no authenticated PRP user reached the tool.
        if (!writeEnabled) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "MCP writing is disabled");
        }
    }

    private String lockTask(long id) {
        if (id <= 0) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid task ID");
        var rows = db.query("SELECT updated_at FROM prp_tasks WHERE id=? AND user_id=? AND deleted=0 FOR UPDATE",
            (rs, n) -> rs.getTimestamp("updated_at").toString(), id, CurrentUser.id());
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Task not found");
        return rows.getFirst();
    }

    @Transactional
    public Preview prepareTaskChange(long id, CreateTaskRequest after, String status, boolean delete) {
        requireWrite();
        if (!delete && after == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Task values required");
        String revision = lockTask(id);
        return prepare(delete ? Kind.TASK_DELETE : Kind.TASK_UPDATE,
            new TaskChange(id, tasks.get(id), revision, delete ? null : after, delete ? null : status));
    }

    private Object applyTaskChange(TaskChange change, boolean delete) {
        String revision = lockTask(change.taskId());
        if (!revision.equals(change.revision()) || !normalized(tasks.get(change.taskId())).equals(normalized(change.before())))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Task changed; prepare and approve a new draft");
        if (delete) {
            tasks.delete(change.taskId());
            return java.util.Map.of("taskId", change.taskId(), "deleted", true);
        }
        var updated = tasks.update(change.taskId(), change.after());
        return change.status() == null ? updated : tasks.updateStatus(change.taskId(), change.status());
    }

    private static com.matrix.prp.tasks.model.TaskItem normalized(com.matrix.prp.tasks.model.TaskItem item) {
        return new com.matrix.prp.tasks.model.TaskItem(item.id(), item.moduleCode(), item.title(),
            item.description(), item.priority(), item.status(), item.dueDate(),
            item.createdAt() == null ? null : item.createdAt().withOffsetSameInstant(java.time.ZoneOffset.UTC),
            item.completedAt() == null ? null : item.completedAt().withOffsetSameInstant(java.time.ZoneOffset.UTC));
    }

    @Transactional
    public Preview prepare(Kind kind, Object request) {
        requireWrite();
        validate(request);
        long owner = CurrentUser.id();
        Integer pending = db.queryForObject(
            "SELECT COUNT(*) FROM prp_mcp_write_drafts WHERE user_id=? AND status='PENDING' AND expires_at > CURRENT_TIMESTAMP",
            Integer.class, owner);
        if (pending != null && pending >= 50) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many pending MCP drafts");
        }
        String id = UUID.randomUUID().toString();
        LocalDateTime expiry = LocalDateTime.now().plusMinutes(15);
        try {
            db.update("INSERT INTO prp_mcp_write_drafts (id,user_id,kind,payload_json,expires_at) VALUES (?,?,?,?,?)",
                id, owner, kind.name(), json.writeValueAsString(request), Timestamp.valueOf(expiry));
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid draft");
        }
        String instruction;
        if (chatApprovalEligible(chatgptApprovalUiEnabled, kind.name(), "PENDING",
                org.springframework.security.core.context.SecurityContextHolder.getContext().getAuthentication())) {
            instruction = "Review the immutable wellness-create draft in the embedded ChatGPT "
                + "approval card. The ordinary confirm tool cannot approve pending drafts. "
                + "Only the app-only approval action can mark this draft approved.";
        } else {
            instruction = "Open " + approvalBase + "me/mcp-approve/" + id
                + " in your own browser, review and enter your PRP password there, never in chat. "
                + "Only then may the MCP client call "
                + (kind.name().startsWith("WELLNESS_") ? "prp_confirm_wellness_draft" : "prp_confirm_draft") + ".";
        }
        return new Preview(id, kind.name(), json.valueToTree(request), expiry.toString(), instruction);
    }

    /** The human reviews the exact owner-bound data through PRP, never through a model-controlled approval flag. */
    public Review review(String draftId) {
        requireWrite();
        validId(draftId);
        List<Review> rows = db.query(
            "SELECT kind,payload_json,status,expires_at FROM prp_mcp_write_drafts WHERE id=? AND user_id=?",
            (rs, n) -> new Review(draftId, rs.getString("kind"), readJson(rs.getString("payload_json")),
                rs.getString("status"), rs.getTimestamp("expires_at").toLocalDateTime().toString()),
            draftId, CurrentUser.id());
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "MCP draft not found");
        return rows.getFirst();
    }

    /**
     * PRP page step-up authentication. A tool call alone cannot mark the draft approved.
     * Wrong password attempts are committed, capped at five per draft, without throwing a rollback.
     */
    @Transactional
    public Approval approve(String draftId, String password) {
        requireWrite();
        validId(draftId);
        if (password == null || password.isBlank() || password.length() > 256)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Password required");
        long owner = CurrentUser.id();
        record Pending(String status, int attempts, LocalDateTime expiresAt) {}
        List<Pending> rows = db.query(
            "SELECT status,approval_failures,expires_at FROM prp_mcp_write_drafts WHERE id=? AND user_id=? FOR UPDATE",
            (rs, n) -> new Pending(rs.getString("status"), rs.getInt("approval_failures"),
                rs.getTimestamp("expires_at").toLocalDateTime()), draftId, owner);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "MCP draft not found");
        Pending row = rows.getFirst();
        if (!"PENDING".equals(row.status()) || !row.expiresAt().isAfter(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "MCP draft not pending");
        if (row.attempts() >= 5) throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Approval locked");
        UserAccount account = users.findById(owner).orElse(null);
        if (account == null || !account.enabled() || !passwords.matches(password, account.passwordHash())) {
            int attempts = row.attempts() + 1;
            db.update("UPDATE prp_mcp_write_drafts SET approval_failures=?,status=? WHERE id=? AND user_id=?",
                attempts, attempts >= 5 ? "REJECTED" : "PENDING", draftId, owner);
            return new Approval(attempts >= 5 ? "LOCKED" : "INVALID_PASSWORD", Math.max(0, 5 - attempts));
        }
        db.update("UPDATE prp_mcp_write_drafts SET status='APPROVED',approved_at=CURRENT_TIMESTAMP " +
            "WHERE id=? AND user_id=? AND status='PENDING'", draftId, owner);
        return new Approval("APPROVED", 0);
    }

    @Transactional
    public void reject(String draftId) {
        requireWrite();
        validId(draftId);
        db.update("UPDATE prp_mcp_write_drafts SET status='REJECTED' WHERE id=? AND user_id=? " +
            "AND status IN ('PENDING','APPROVED')", draftId, CurrentUser.id());
    }

    private static void validId(String draftId) {
        try {
            UUID.fromString(draftId);
        } catch (RuntimeException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid draft ID");
        }
    }

    /**
     * Only the trusted ChatGPT MCP Apps UI is offered an approval action, not
     * the model-visible confirm tool. Host-enforced app-only visibility is a
     * separate boundary; the server still enforces verified client and scopes.
     * This is not proof of an external human identity beyond ChatGPT OAuth.
     */
    static boolean chatApprovalEligible(boolean enabled, String kind, String status,
                                        org.springframework.security.core.Authentication auth) {
        if (!enabled || !"WELLNESS_CREATE".equals(kind) || !"PENDING".equals(status)
                || auth == null || !auth.isAuthenticated()
                || !(auth.getDetails() instanceof McpScopeGuard.VerifiedClient client)
                || !"https://chatgpt.com/oauth/client.json".equals(client.clientId())) {
            return false;
        }
        return java.util.Set.of("SCOPE_prp.wellness.write.confirm", "SCOPE_prp.wellness.write.create")
            .stream().allMatch(scope -> auth.getAuthorities().stream()
                .anyMatch(authority -> scope.equals(authority.getAuthority())));
    }

    /**
     * App-only UI approval. Requires the host to enforce _meta.ui.visibility=[app].
     * Never accepts user IDs, model-supplied approval booleans, or passwords.
     * Pending drafts are still NOT writable through confirm until this transaction
     * records an explicit approved status.
     */
    @Transactional
    public Approval approveFromChatgptUi(String draftId, String decision) {
        requireWrite();
        validId(draftId);
        if (!"approve".equals(decision) && !"reject".equals(decision))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid approval decision");
        var auth = org.springframework.security.core.context.SecurityContextHolder.getContext().getAuthentication();
        long owner = CurrentUser.id();
        record Pending(String kind, String status, LocalDateTime expiresAt) {}
        var rows = db.query(
            "SELECT kind,status,expires_at FROM prp_mcp_write_drafts WHERE id=? AND user_id=? FOR UPDATE",
            (rs,n) -> new Pending(rs.getString("kind"), rs.getString("status"),
                rs.getTimestamp("expires_at").toLocalDateTime()),
            draftId, owner);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "MCP draft not found");
        var row = rows.getFirst();
        if (!chatApprovalEligible(chatgptApprovalUiEnabled, row.kind(), row.status(), auth)
                || !row.expiresAt().isAfter(LocalDateTime.now()))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "ChatGPT UI approval not permitted");
        String status = "approve".equals(decision) ? "APPROVED" : "REJECTED";
        if (db.update(
            "UPDATE prp_mcp_write_drafts SET status=? WHERE id=? AND user_id=? AND status='PENDING'",
            status, draftId, owner) != 1)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Draft approval raced");
        return new Approval(status, 0);
    }

    @Transactional
    public Result confirm(String draftId) {
        requireWrite();
        validId(draftId);
        long owner = CurrentUser.id();
        List<Stored> rows = db.query(
            "SELECT kind,payload_json,result_json,status,expires_at FROM prp_mcp_write_drafts " +
                "WHERE id=? AND user_id=? FOR UPDATE",
            (rs, n) -> new Stored(rs.getString("kind"), rs.getString("payload_json"),
                rs.getString("result_json"), rs.getString("status"),
                rs.getTimestamp("expires_at").toLocalDateTime()),
            draftId, owner);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "MCP draft not found");
        }
        Stored row = rows.getFirst();
        if ("CONSUMED".equals(row.status())) {
            return new Result(draftId, row.kind(), readJson(row.result()), true);
        }
        if (!"APPROVED".equals(row.status()) || !row.expiresAt().isAfter(LocalDateTime.now())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "MCP draft expired or invalid");
        }
        JsonNode saved;
        try {
            Object request = switch (Kind.valueOf(row.kind())) {
                case TASK -> json.readValue(row.payload(), CreateTaskRequest.class);
                case FINANCE -> json.readValue(row.payload(), CreateFinanceTransactionRequest.class);
                case RECORD -> json.readValue(row.payload(), CreateRecordRequest.class);
                case TASK_UPDATE, TASK_DELETE -> json.readValue(row.payload(), TaskChange.class);
                case WELLNESS_CREATE, WELLNESS_UPDATE, WELLNESS_DELETE -> json.readValue(row.payload(), McpWellnessSupport.Change.class);
            };
            validate(request);
            Object result = switch (Kind.valueOf(row.kind())) {
                case TASK -> tasks.create((CreateTaskRequest) request);
                case FINANCE -> finance.createTransaction((CreateFinanceTransactionRequest) request);
                case RECORD -> records.create((CreateRecordRequest) request);
                case TASK_UPDATE -> applyTaskChange((TaskChange) request, false);
                case TASK_DELETE -> applyTaskChange((TaskChange) request, true);
                case WELLNESS_CREATE -> health().apply((McpWellnessSupport.Change) request, draftId, true, false);
                case WELLNESS_UPDATE -> health().apply((McpWellnessSupport.Change) request, draftId, false, false);
                case WELLNESS_DELETE -> health().apply((McpWellnessSupport.Change) request, draftId, false, true);
            };
            // Normalize persisted and first-response decimal nodes through the same codec.
            saved = json.readTree(json.writeValueAsString(result));
            if (db.update("UPDATE prp_mcp_write_drafts SET status='CONSUMED', result_json=?, consumed_at=CURRENT_TIMESTAMP " +
                    "WHERE id=? AND user_id=? AND status='APPROVED'",
                    json.writeValueAsString(saved), draftId, owner) != 1) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "MCP draft already consumed");
            }
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid MCP draft payload");
        }
        return new Result(draftId, row.kind(), saved, false);
    }

    private JsonNode readJson(String raw) {
        try {
            return json.readTree(raw);
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Unreadable prior result");
        }
    }

    private void validate(Object request) {
        if (!validator.validate(request).isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid business fields");
        }
        if (request instanceof McpWellnessSupport.Change change) {
            health().validateChange(change, change.recordId()==0, change.after()==null);
        } else if (request instanceof TaskChange change) {
            if (change.taskId() <= 0 || change.before() == null || change.before().id() != change.taskId()
                || change.revision() == null || change.revision().isBlank())
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid task change");
            if (change.after() != null) validate(change.after());
            if (change.status() != null && !List.of("todo", "in_progress", "done", "canceled").contains(change.status()))
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid task status");
        } else if (request instanceof CreateTaskRequest t) {
            length(t.moduleCode(), 1, 40); length(t.title(), 1, 160);
            length(t.description(), 0, 4000);
        } else if (request instanceof CreateFinanceTransactionRequest f) {
            length(f.category(), 1, 80); length(f.account(), 0, 80);
            length(f.merchant(), 0, 160); length(f.note(), 0, 2000);
            if (f.amount() == null || f.amount().signum() <= 0 ||
                f.amount().compareTo(new java.math.BigDecimal("100000000")) > 0) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid amount");
            }
        } else if (request instanceof CreateRecordRequest r) {
            length(r.moduleCode(), 1, 40); length(r.title(), 1, 160);
            length(r.content(), 0, 10000);
        } else {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported request");
        }
    }

    private static void length(String value, int min, int max) {
        if ((value == null && min > 0) ||
            (value != null && (value.isBlank() && min > 0 || value.length() > max ||
                value.length() < min))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid field length");
        }
    }
}
