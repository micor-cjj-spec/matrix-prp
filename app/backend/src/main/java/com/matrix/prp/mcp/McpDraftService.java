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
    public enum Kind { TASK, FINANCE, RECORD }
    public record Preview(String draftId, String kind, JsonNode values, String expiresAt,
                          String instruction) {}
    public record Result(String draftId, String kind, JsonNode saved, boolean alreadySaved) {}
    public record Review(String draftId, String kind, JsonNode values, String status, String expiresAt) {}
    public record Approval(String status, int remainingAttempts) {}
    private record Stored(String kind, String payload, String result, String status,
                          LocalDateTime expiresAt) {}

    private final JdbcTemplate db;
    private final ObjectMapper json;
    private final Validator validator;
    private final TaskService tasks;
    private final FinanceService finance;
    private final RecordService records;
    private final boolean writeEnabled;
    private final UserStore users;
    private final PasswordEncoder passwords;

    public McpDraftService(JdbcTemplate db, ObjectMapper json, Validator validator,
                           TaskService tasks, FinanceService finance, RecordService records,
                           UserStore users, PasswordEncoder passwords,
                           @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled) {
        this.db = db;
        this.json = json;
        this.validator = validator;
        this.tasks = tasks;
        this.finance = finance;
        this.records = records;
        this.writeEnabled = writeEnabled;
        this.users = users;
        this.passwords = passwords;
    }

    private void requireWrite() {
        CurrentUser.id(); // Fail closed if no authenticated PRP user reached the tool.
        if (!writeEnabled) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "MCP writing is disabled");
        }
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
        return new Preview(id, kind.name(), json.valueToTree(request), expiry.toString(),
            "Open PRP /me/mcp-approve/" + id + " in your own browser, review and enter your PRP password. Only then may the MCP client call prp_confirm_draft.");
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
            };
            validate(request);
            Object result = switch (Kind.valueOf(row.kind())) {
                case TASK -> tasks.create((CreateTaskRequest) request);
                case FINANCE -> finance.createTransaction((CreateFinanceTransactionRequest) request);
                case RECORD -> records.create((CreateRecordRequest) request);
            };
            saved = json.valueToTree(result);
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
        if (request instanceof CreateTaskRequest t) {
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
